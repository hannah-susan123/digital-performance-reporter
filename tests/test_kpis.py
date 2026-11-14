import math

import pandas as pd
import pytest

from reporter import kpis


def campaigns(rows):
    df = pd.DataFrame(rows, columns=["channel", "impressions", "clicks", "conversions", "spend", "revenue"])
    return kpis.campaign_kpis(df)


def test_campaign_ratios():
    c = campaigns([["Email", 1000, 50, 10, 200.0, 800.0]]).iloc[0]
    assert c["ctr"] == pytest.approx(0.05)
    assert c["conversion_rate"] == pytest.approx(0.2)
    assert c["cpc"] == pytest.approx(4.0)
    assert c["cost_per_conversion"] == pytest.approx(20.0)
    assert c["roas"] == pytest.approx(4.0)
    assert c["roi"] == pytest.approx(3.0)


def test_divide_by_zero_gives_nan_not_error():
    c = campaigns([["Email", 0, 0, 0, 0.0, 100.0]]).iloc[0]
    assert math.isnan(c["ctr"]) and math.isnan(c["roas"])


def test_group_ratios_use_totals_not_averages():
    # one big and one small campaign: average of ROAS would be (2 + 10) / 2 = 6
    df = campaigns([
        ["Email", 1000, 100, 10, 1000.0, 2000.0],
        ["Email", 100, 10, 1, 10.0, 100.0],
    ])
    row = kpis.summarise(df, "channel").iloc[0]
    assert row["campaigns"] == 2
    assert row["roas"] == pytest.approx(2100 / 1010)


def test_summary_sorted_best_first_with_gap_to_average():
    df = campaigns([
        ["Email", 1000, 100, 10, 100.0, 300.0],
        ["SEO", 1000, 100, 10, 100.0, 100.0],
    ])
    t = kpis.summarise(df, "channel")
    assert list(t["channel"]) == ["Email", "SEO"]
    # overall ROAS is 2.0, Email is 3.0 -> +50%
    assert t.loc[0, "roas_vs_avg"] == pytest.approx(0.5)


def test_duration_bands(cfg):
    df = pd.DataFrame({"duration": [3, 7, 8, 21, 30]})
    bands = kpis.add_duration_band(df, cfg)["duration_band"].astype(str).tolist()
    assert bands == ["1-7 days", "1-7 days", "8-14 days", "15-21 days", "22+ days"]


def test_platform_breakdown_counts_each_platform():
    df = campaigns([["Email", 1000, 100, 10, 100.0, 300.0]])
    df["platform"] = "WhatsApp, YouTube"
    t = kpis.platform_breakdown(df)
    assert sorted(t["platform"]) == ["WhatsApp", "YouTube"]
    assert t["revenue"].sum() == 600  # double counted on purpose
