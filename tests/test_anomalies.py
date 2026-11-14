import pandas as pd
import pytest

from reporter import kpis
from reporter.config import ConfigError, build_config
from reporter.formatting import MINUS, money, pct, signed_pct
from tests.conftest import COLUMNS


def weekly_data(revenues, per_week=10, last_week_days=7):
    """Campaigns spread over consecutive Monday-start weeks with given weekly revenue."""
    rows = []
    start = pd.Timestamp("2025-01-06")  # a Monday
    for w, revenue in enumerate(revenues):
        days = last_week_days if w == len(revenues) - 1 else 7
        for i in range(per_week):
            rows.append({
                "channel": "Email", "impressions": 1000, "clicks": 100, "conversions": 10,
                "spend": 100.0, "revenue": revenue / per_week,
                "date": start + pd.Timedelta(days=7 * w + i % days),
            })
    return kpis.campaign_kpis(pd.DataFrame(rows))


def test_week_on_week_change_over_threshold_is_flagged():
    t = kpis.weekly_trend(weekly_data([1000, 1050, 700, 720]), change_threshold=0.2)
    assert t["anomaly"].tolist() == [False, False, True, False]
    assert f"Revenue {MINUS}33%" in t.loc[2, "note"]  # real minus sign, never splits from the number


def test_small_changes_are_not_flagged():
    t = kpis.weekly_trend(weekly_data([1000, 1100, 1000, 1150]), change_threshold=0.2)
    assert not t["anomaly"].any()


def test_partial_final_week_is_not_flagged():
    # last week only has 2 days of data, so its drop isn't a real anomaly
    t = kpis.weekly_trend(weekly_data([1000, 1000, 300], last_week_days=2), change_threshold=0.2)
    assert t["partial"].tolist() == [False, False, True]
    assert not t["anomaly"].any()


def channel_campaigns(revenues, channel="Email"):
    """Campaigns with spend 100 each, so ROI = revenue / 100 - 1 and cost per conversion is constant."""
    rows = [{"channel": channel, "impressions": 1000, "clicks": 100, "conversions": 10,
             "spend": 100.0, "revenue": float(r)} for r in revenues]
    df = kpis.campaign_kpis(pd.DataFrame(rows))
    df["campaign"] = [f"{channel}{i}" for i in range(len(df))]
    return df


# z-score method

def test_zscore_flags_campaign_far_from_channel_mean():
    df = pd.concat([
        channel_campaigns([200 + i for i in range(20)] + [5000]),
        channel_campaigns([5000], channel="SEO"),  # only SEO campaign: nothing to compare to
    ], ignore_index=True)
    out = kpis.campaign_outliers(df, method="zscore", z_threshold=3.0)
    assert out["campaign"].tolist() == ["Email20"]
    assert "ROI above" in out.loc[0, "reason"]


def test_no_outliers_in_uniform_data():
    df = channel_campaigns([200 + i for i in range(20)])
    assert kpis.campaign_outliers(df, method="zscore").empty
    assert kpis.campaign_outliers(df, method="iqr").empty


# IQR method

def test_iqr_flags_high_and_low_values():
    df = channel_campaigns([200 + i for i in range(20)] + [5000, 10])
    out = kpis.campaign_outliers(df, method="iqr")
    assert sorted(out["campaign"]) == ["Email20", "Email21"]
    reasons = dict(zip(out["campaign"], out["reason"]))
    assert "ROI above" in reasons["Email20"]
    assert "ROI below" in reasons["Email21"]


def test_iqr_score_is_distance_past_the_fence():
    # ROIs 1,1,2,2,3,3,4,4,19 -> Q1=2, Q3=4, IQR=2, upper fence 4 + 1.5*2 = 7
    df = channel_campaigns([200, 200, 300, 300, 400, 400, 500, 500, 2000])
    out = kpis.campaign_outliers(df, method="iqr", iqr_multiplier=1.5)
    assert out["campaign"].tolist() == ["Email8"]
    assert out.loc[0, "return_score"] == pytest.approx((19 - 7) / 2)


def test_iqr_multiplier_moves_the_fence():
    # same data: fence is 4 + k*2, so 19 is flagged at k=7 (fence 18) but not k=8 (fence 20)
    df = channel_campaigns([200, 200, 300, 300, 400, 400, 500, 500, 2000])
    assert len(kpis.campaign_outliers(df, method="iqr", iqr_multiplier=7)) == 1
    assert kpis.campaign_outliers(df, method="iqr", iqr_multiplier=8).empty


def test_iqr_catches_extremes_that_mask_themselves_in_zscore():
    # three huge values inflate the standard deviation, so none reaches z = 3
    df = channel_campaigns([200 + i for i in range(20)] + [5000, 5000, 5000])
    assert kpis.campaign_outliers(df, method="zscore", z_threshold=3.0).empty
    assert len(kpis.campaign_outliers(df, method="iqr")) == 3


def test_unknown_outlier_method_is_rejected():
    df = channel_campaigns([200, 300])
    with pytest.raises(ValueError):
        kpis.campaign_outliers(df, method="median")
    with pytest.raises(ConfigError):
        build_config({"columns": dict(COLUMNS), "outlier_method": "median"})


# log IQR method (default)
# ROAS 1,1,2,2,4,4,8,8 and one at 1/16. On a log2 scale that's 0,0,1,1,2,2,3,3 and -4.
# Q1 = 0, Q3 = 2, IQR = 2 -> lower fence 0 - 1.5*2 = -3 (ROAS 2^-3 = 0.125), upper fence 5 (ROAS 32).
WORKED_EXAMPLE = [100, 100, 200, 200, 400, 400, 800, 800, 6.25]  # revenue on spend of 100


def test_log_iqr_worked_example():
    df = channel_campaigns(WORKED_EXAMPLE)
    out = kpis.campaign_outliers(df, method="log_iqr", iqr_multiplier=1.5)
    assert out["campaign"].tolist() == ["Email8"]
    row = out.iloc[0]
    assert row["outlier_type"] == "Low return"
    assert row["roas_lower_limit"] == pytest.approx(0.125)
    # one log2 step below the fence, IQR of 2 log2 steps -> -0.5
    assert row["return_score"] == pytest.approx(-0.5)


def test_log_iqr_catches_low_return_that_plain_iqr_misses():
    df = channel_campaigns(WORKED_EXAMPLE)
    # on raw ROI the lower fence is 0 - 1.5*3 = -4.5, and ROI can never go below -1
    plain = kpis.campaign_outliers(df, method="iqr")
    assert plain.empty
    assert len(kpis.campaign_outliers(df, method="log_iqr")) == 1


def test_log_iqr_flags_high_returns_too():
    df = channel_campaigns(WORKED_EXAMPLE + [25600])  # ROAS 256 = 2^8
    out = kpis.campaign_outliers(df, method="log_iqr")
    assert dict(zip(out["campaign"], out["outlier_type"])) == {
        "Email8": "Low return", "Email9": "High return",
    }


def test_log_iqr_handles_zero_revenue():
    df = channel_campaigns(WORKED_EXAMPLE[:-1] + [0])
    out = kpis.campaign_outliers(df, method="log_iqr")
    assert out["campaign"].tolist() == ["Email8"]
    assert out.loc[0, "outlier_type"] == "Low return"


def test_action_list_is_low_return_only_biggest_loss_first():
    df = pd.concat([
        channel_campaigns(WORKED_EXAMPLE + [25600]),
        channel_campaigns([100, 100, 200, 200, 400, 400, 800, 800, 2], channel="SEO"),
    ], ignore_index=True)
    action = kpis.action_list(kpis.campaign_outliers(df, method="log_iqr"))
    assert action["campaign"].tolist() == ["SEO8", "Email8"]  # lost 98 vs 93.75
    assert (action["outlier_type"] == "Low return").all()


def test_log_iqr_is_the_default(cfg):
    assert cfg["outlier_method"] == "log_iqr"


def test_negative_numbers_use_a_real_minus_sign():
    for text in [signed_pct(-0.29), pct(-0.05), money(-250000)]:
        assert "-" not in text and MINUS in text
    assert signed_pct(0.12) == "+12%"
