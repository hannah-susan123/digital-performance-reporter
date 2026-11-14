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


OUTLIER_METHODS = ("iqr", "zscore")
OUTLIER_METRICS = {"roi": "ROI", "cost_per_conversion": "Cost per conversion"}


def _zscore_scores(values, groups, z_threshold):
    """Standard deviations from the channel mean; flagged beyond +/- z_threshold."""
    mean = groups.transform("mean")
    std = groups.transform("std")
    score = safe_divide(values - mean, std)
    return score, score.abs() > z_threshold


def _iqr_scores(values, groups, multiplier):
    """Flag values beyond Q1 - k*IQR or Q3 + k*IQR within the channel.

    Score is how many IQRs past the fence the value sits (0 if inside).
    """
    q1 = groups.transform(lambda s: s.quantile(0.25))
    q3 = groups.transform(lambda s: s.quantile(0.75))
    iqr = q3 - q1
    low, high = q1 - multiplier * iqr, q3 + multiplier * iqr
    flagged = (values < low) | (values > high)
    # positive above the upper fence, negative below the lower one, 0 inside
    past_fence = (values - high).clip(lower=0) - (low - values).clip(lower=0)
    return safe_divide(past_fence, iqr), flagged


def campaign_outliers(campaigns: pd.DataFrame, method="iqr", z_threshold=3.0,
                      iqr_multiplier=1.5) -> pd.DataFrame:
    """Campaigns whose ROI or cost per conversion is unusual for their channel.

    method="iqr" suits skewed metrics like ROI; "zscore" assumes a roughly
    symmetric spread and over-flags the long tail.
    """
    if method not in OUTLIER_METHODS:
        raise ValueError(f"outlier_method must be one of {OUTLIER_METHODS}, got {method!r}")
    c = campaigns.copy()
    flags = []
    for metric in OUTLIER_METRICS:
        groups = c.groupby("channel")[metric]
        if method == "iqr":
            score, flag = _iqr_scores(c[metric], groups, iqr_multiplier)
        else:
            score, flag = _zscore_scores(c[metric], groups, z_threshold)
        c[f"{metric}_score"] = score
        c[f"{metric}_flag"] = flag
        flags.append(flag)

    rule = f"more than {z_threshold:g} std devs" if method == "zscore" else f"beyond {iqr_multiplier:g}x IQR"

    def reason(row):
        parts = []
        for metric, label in OUTLIER_METRICS.items():
            if row[f"{metric}_flag"]:
                side = "above" if row[f"{metric}_score"] > 0 else "below"
                parts.append(f"{label} {side} channel norm ({rule})")
        return "; ".join(parts)

    flagged = c[flags[0] | flags[1]].copy()
    flagged["reason"] = flagged.apply(reason, axis=1) if len(flagged) else pd.Series(dtype=str)
    flagged["max_score"] = flagged[["roi_score", "cost_per_conversion_score"]].abs().max(axis=1)
    flagged = flagged.drop(columns=[f"{m}_flag" for m in OUTLIER_METRICS])
    return flagged.sort_values("max_score", ascending=False).reset_index(drop=True)
