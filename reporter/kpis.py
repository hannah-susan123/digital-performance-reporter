"""KPI calculations, breakdowns, weekly trend and outlier detection."""
import numpy as np
import pandas as pd

SUM_COLUMNS = ["impressions", "clicks", "conversions", "spend", "revenue"]


def safe_divide(numerator, denominator):
    """Divide, returning NaN instead of inf when the denominator is 0."""
    if np.isscalar(denominator):
        return numerator / denominator if denominator else np.nan
    return numerator / denominator.where(denominator != 0)


def add_ratios(t: pd.DataFrame) -> pd.DataFrame:
    t["ctr"] = safe_divide(t["clicks"], t["impressions"])
    t["conversion_rate"] = safe_divide(t["conversions"], t["clicks"])
    t["cpc"] = safe_divide(t["spend"], t["clicks"])
    t["cost_per_conversion"] = safe_divide(t["spend"], t["conversions"])
    t["roas"] = safe_divide(t["revenue"], t["spend"])
    t["roi"] = safe_divide(t["revenue"] - t["spend"], t["spend"])
    return t


def campaign_kpis(df: pd.DataFrame) -> pd.DataFrame:
    """KPIs for each campaign row."""
    return add_ratios(df.copy())


def overall_kpis(df: pd.DataFrame) -> dict:
    totals = df[SUM_COLUMNS].sum()
    t = add_ratios(totals.to_frame().T.astype(float)).iloc[0]
    result = t.to_dict()
    result["campaigns"] = len(df)
    return result


def summarise(df: pd.DataFrame, by: str, sort_by="roas") -> pd.DataFrame:
    """Sum the volumes per group, then work out ratios from the totals.

    Ratios come from totals, not an average of each campaign's ratio, so big
    campaigns count for more than small ones.
    """
    groups = df.groupby(by, observed=True)
    t = groups[SUM_COLUMNS].sum()
    t.insert(0, "campaigns", groups.size())
    t = add_ratios(t)
    overall_roas = safe_divide(df["revenue"].sum(), df["spend"].sum())
    t["roas_vs_avg"] = t["roas"] / overall_roas - 1
    if sort_by:
        t = t.sort_values(sort_by, ascending=False)
    return t.reset_index()


def add_duration_band(df: pd.DataFrame, cfg) -> pd.DataFrame:
    bands = cfg["duration_bands"]
    df = df.copy()
    df["duration_band"] = pd.cut(
        df["duration"], bins=[float(e) for e in bands["edges"]], labels=bands["labels"]
    )
    return df


def platform_breakdown(df: pd.DataFrame, separator=",") -> pd.DataFrame:
    """A campaign on "WhatsApp, YouTube" counts once for each platform,
    so these totals add up to more than the overall total."""
    exploded = df.assign(platform=df["platform"].str.split(separator)).explode("platform")
    exploded["platform"] = exploded["platform"].str.strip()
    return summarise(exploded, "platform")


def weekly_trend(df: pd.DataFrame, change_threshold=0.20, partial_ratio=0.5) -> pd.DataFrame:
    """Weekly totals with week-on-week change and anomaly flags.

    A week is partial if the data doesn't cover all seven days of it, or if it
    has far fewer campaigns than a normal week. Partial weeks are shown but
    never flagged, and changes skip over them.
    """
    dated = df.dropna(subset=["date"])
    week = dated["date"].dt.to_period("W-SUN").dt.start_time
    t = summarise(dated.assign(week=week), "week", sort_by=None).sort_values("week")

    first, last = dated["date"].min().normalize(), dated["date"].max().normalize()
    fully_covered = (t["week"] >= first) & (t["week"] + pd.Timedelta(days=6) <= last)
    low_volume = t["campaigns"] < partial_ratio * t["campaigns"].median()
    t["partial"] = ~fully_covered | low_volume

    full = t[~t["partial"]]
    t["revenue_change"] = full["revenue"].pct_change()
    t["roas_change"] = full["roas"].pct_change()
    t["campaigns_change"] = full["campaigns"].pct_change()
    t["anomaly"] = (t["revenue_change"].abs() > change_threshold) | (
        t["roas_change"].abs() > change_threshold
    )

    def note(row):
        if row["partial"]:
            return "Partial week"
        parts = []
        if abs(row["revenue_change"]) > change_threshold:
            parts.append(f"Revenue {row['revenue_change']:+.0%} vs previous week")
        if abs(row["roas_change"]) > change_threshold:
            parts.append(f"ROAS {row['roas_change']:+.0%} vs previous week")
        return "; ".join(parts)

    t["note"] = t.apply(note, axis=1)
    return t.reset_index(drop=True)


OUTLIER_METHODS = ("log_iqr", "iqr", "zscore")
MIN_ROAS = 0.001  # log(0) is undefined, so zero-revenue campaigns count as ROAS 0.001


def _limits(values, channel, method, z_threshold, iqr_multiplier):
    """Lower and upper limit for each row, from its own channel's spread.

    Returns (low, high, score). The score is how far past the nearest limit a
    value sits, in units of the spread (IQR or std dev): negative below, positive
    above, 0 inside.
    """
    groups = values.groupby(channel)
    if method == "zscore":
        mean, spread = groups.transform("mean"), groups.transform("std")
        low, high = mean - z_threshold * spread, mean + z_threshold * spread
    else:
        q1 = groups.transform(lambda s: s.quantile(0.25))
        q3 = groups.transform(lambda s: s.quantile(0.75))
        spread = q3 - q1
        low, high = q1 - iqr_multiplier * spread, q3 + iqr_multiplier * spread
    past_limit = (values - high).clip(lower=0) - (low - values).clip(lower=0)
    return low, high, safe_divide(past_limit, spread).fillna(0)


def campaign_outliers(campaigns: pd.DataFrame, method="log_iqr", z_threshold=3.0,
                      iqr_multiplier=1.5) -> pd.DataFrame:
    """Campaigns whose return or cost per conversion is unusual for their channel.

    log_iqr: IQR rule on log(ROAS) and log(cost per conversion). Both are
             positive and right-skewed; on a log scale they're roughly symmetric,
             so the fences catch unusually low returns as well as high ones.
    iqr:     IQR rule on ROI and cost per conversion as they are.
    zscore:  more than z_threshold std devs from the channel mean.
    """
    if method not in OUTLIER_METHODS:
        raise ValueError(f"outlier_method must be one of {OUTLIER_METHODS}, got {method!r}")
    c = campaigns.copy()

    if method == "log_iqr":
        ret = np.log(c["roas"].clip(lower=MIN_ROAS))
        cost = np.log(c["cost_per_conversion"].where(c["cost_per_conversion"] > 0))
        ret_label, rule = "Return (ROAS)", f"beyond {iqr_multiplier:g}x IQR on log scale"
    else:
        ret, cost = c["roi"], c["cost_per_conversion"]
        ret_label = "ROI"
        rule = f"beyond {iqr_multiplier:g}x IQR" if method == "iqr" else f"more than {z_threshold:g} std devs"

    ret_low, _, c["return_score"] = _limits(ret, c["channel"], method, z_threshold, iqr_multiplier)
    _, _, c["cost_score"] = _limits(cost, c["channel"], method, z_threshold, iqr_multiplier)

    # the channel's lower return limit, always shown as ROAS so every method reads the same
    c["roas_lower_limit"] = np.exp(ret_low) if method == "log_iqr" else ret_low + 1
    c["loss"] = c["spend"] - c["revenue"]

    def reason(row):
        parts = []
        for score, label in [(row["return_score"], ret_label), (row["cost_score"], "Cost per conversion")]:
            if score:
                parts.append(f"{label} {'above' if score > 0 else 'below'} channel norm ({rule})")
        return "; ".join(parts)

    def outlier_type(row):
        if row["return_score"] < 0:
            return "Low return"
        if row["return_score"] > 0:
            return "High return"
        return "High cost per conversion" if row["cost_score"] > 0 else "Low cost per conversion"

    flagged = c[(c["return_score"] != 0) | (c["cost_score"] != 0)].copy()
    if flagged.empty:
        return flagged.assign(reason=pd.Series(dtype=str), outlier_type=pd.Series(dtype=str))
    flagged["reason"] = flagged.apply(reason, axis=1)
    flagged["outlier_type"] = flagged.apply(outlier_type, axis=1)
    # low-return campaigns first (biggest loss first): they're the action list
    flagged["_order"] = (flagged["outlier_type"] != "Low return").astype(int)
    flagged = flagged.sort_values(["_order", "loss"], ascending=[True, False])
    return flagged.drop(columns="_order").reset_index(drop=True)


def action_list(outliers: pd.DataFrame) -> pd.DataFrame:
    """Low-return outliers, biggest loss first."""
    if outliers.empty:
        return outliers
    return outliers[outliers["outlier_type"] == "Low return"].reset_index(drop=True)
