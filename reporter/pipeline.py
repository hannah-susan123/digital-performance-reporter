"""Runs clean -> KPIs -> insights and holds the results in one object."""
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from . import kpis
from .clean import QualityReport, clean_data
from .insights import Insights, generate_insights


@dataclass
class ReportData:
    source: str
    quality: QualityReport
    campaigns: pd.DataFrame
    overall: dict
    by_channel: pd.DataFrame
    by_segment: Optional[pd.DataFrame]
    by_duration: Optional[pd.DataFrame]
    by_platform: Optional[pd.DataFrame]
    weekly: Optional[pd.DataFrame]
    outliers: pd.DataFrame
    action_list: pd.DataFrame
    top: pd.DataFrame
    bottom: pd.DataFrame
    insights: Optional[Insights] = None
    date_range: Optional[tuple] = None


def build_report(raw: pd.DataFrame, cfg, source="data") -> ReportData:
    df, quality = clean_data(raw, cfg)
    if df.empty:
        raise ValueError("No rows left after cleaning - check the data and config.yaml")

    campaigns = kpis.campaign_kpis(df)
    has = campaigns.columns
    th = cfg["thresholds"]
    n = cfg["report"]["top_n_campaigns"]

    if "duration" in has:
        campaigns = kpis.add_duration_band(campaigns, cfg)

    dated = "date" in has and campaigns["date"].notna().any()
    data = ReportData(
        source=source,
        quality=quality,
        campaigns=campaigns,
        overall=kpis.overall_kpis(campaigns),
        by_channel=kpis.summarise(campaigns, "channel"),
        by_segment=kpis.summarise(campaigns, "segment") if "segment" in has else None,
        by_duration=(
            kpis.summarise(campaigns, "duration_band", sort_by=None) if "duration" in has else None
        ),
        by_platform=(
            kpis.platform_breakdown(campaigns, cfg["platform_separator"]) if "platform" in has else None
        ),
        weekly=kpis.weekly_trend(campaigns, th["week_change"], th["partial_week_ratio"]) if dated else None,
        # outlier check runs either way; with no dates it's the main anomaly check
        outliers=kpis.campaign_outliers(
            campaigns, cfg["outlier_method"], th["outlier_z"], th["iqr_multiplier"]
        ),
        action_list=pd.DataFrame(),
        top=campaigns.nlargest(n, "roi"),
        bottom=campaigns.nsmallest(n, "roi"),
        date_range=(campaigns["date"].min(), campaigns["date"].max()) if dated else None,
    )
    data.action_list = kpis.action_list(data.outliers)
    data.insights = generate_insights(data, cfg)
    return data
