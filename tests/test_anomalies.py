import pandas as pd

from reporter import kpis


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
    assert "Revenue -33%" in t.loc[2, "note"]


def test_small_changes_are_not_flagged():
    t = kpis.weekly_trend(weekly_data([1000, 1100, 1000, 1150]), change_threshold=0.2)
    assert not t["anomaly"].any()


def test_partial_final_week_is_not_flagged():
    # last week only has 2 days of data, so its drop isn't a real anomaly
    t = kpis.weekly_trend(weekly_data([1000, 1000, 300], last_week_days=2), change_threshold=0.2)
    assert t["partial"].tolist() == [False, False, True]
    assert not t["anomaly"].any()


def test_outlier_campaign_is_flagged_against_its_channel():
    rows = [{"channel": "Email", "impressions": 1000, "clicks": 100, "conversions": 10,
             "spend": 100.0, "revenue": 200.0 + i} for i in range(20)]
    rows.append({"channel": "Email", "impressions": 1000, "clicks": 100, "conversions": 10,
                 "spend": 100.0, "revenue": 5000.0})
    rows.append({"channel": "SEO", "impressions": 1000, "clicks": 100, "conversions": 10,
                 "spend": 100.0, "revenue": 5000.0})  # only SEO campaign: nothing to compare to
    df = kpis.campaign_kpis(pd.DataFrame(rows))
    df["campaign"] = [f"C{i}" for i in range(len(df))]
    out = kpis.campaign_outliers(df, z_threshold=3.0)
    assert out["campaign"].tolist() == ["C20"]
    assert "ROI far above" in out.loc[0, "reason"]


def test_no_outliers_in_uniform_data():
    rows = [{"channel": "Email", "impressions": 1000, "clicks": 100, "conversions": 10,
             "spend": 100.0, "revenue": 200.0 + i} for i in range(20)]
    df = kpis.campaign_kpis(pd.DataFrame(rows)).assign(campaign="x")
    assert kpis.campaign_outliers(df, z_threshold=3.0).empty
