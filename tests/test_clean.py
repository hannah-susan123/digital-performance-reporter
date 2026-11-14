import pandas as pd
import pytest

from reporter.clean import clean_data
from reporter.config import ConfigError, build_config, standardise_columns
from tests.conftest import COLUMNS, make_row


def test_clean_data_keeps_valid_rows(cfg, make_df):
    df, report = clean_data(make_df([make_row(1), make_row(2)]), cfg)
    assert len(df) == 2
    assert report.rows_removed == 0
    # spend comes from cost per conversion x conversions
    assert df.loc[0, "spend"] == 500


def test_duplicate_rows_are_removed(cfg, make_df):
    df, report = clean_data(make_df([make_row(1), make_row(1), make_row(2)]), cfg)
    assert len(df) == 2
    assert report.found("Duplicate rows") == 1


def test_impossible_values_are_removed(cfg, make_df):
    rows = [
        make_row(1),
        make_row(2, impr=100, clicks=500),   # clicks > impressions
        make_row(3, cpa=-5.0),               # negative spend
        make_row(4, clicks=5, conv=10),      # conversions > clicks
    ]
    df, report = clean_data(make_df(rows), cfg)
    assert list(df["campaign"]) == ["C1"]
    assert report.found("Clicks greater than impressions") == 1
    assert report.found("Negative spend") == 1
    assert report.found("Conversions greater than clicks") == 1


def test_missing_values(cfg, make_df):
    rows = [make_row(1), make_row(2, seg=None), make_row(3)]
    rows[2]["rev"] = None  # core number missing -> unusable
    df, report = clean_data(make_df(rows), cfg)
    assert len(df) == 2
    assert report.found("Missing core values") == 1
    assert report.found("Missing segment") == 1
    assert "Unknown" in set(df["segment"])


def test_conversion_rate_outside_range(make_df):
    columns = {k: v for k, v in COLUMNS.items() if k != "conversions"}
    columns["conversion_rate"] = "cr"
    cfg = build_config({"columns": columns})
    raw = make_df([make_row(1), make_row(2), make_row(3)]).assign(cr=[10.0, 150.0, -2.0])
    df, report = clean_data(raw, cfg)
    assert len(df) == 1
    assert report.found("Conversion rate outside 0-100%") == 2
    # conversions = clicks x rate when there's no conversions column
    assert df.loc[0, "conversions"] == 10


def test_reported_roi_mismatch_is_flagged_not_removed(cfg, make_df):
    rows = [make_row(1), make_row(2)]
    rows[1]["roi"] = 9.99
    df, report = clean_data(make_df(rows), cfg)
    assert len(df) == 2
    assert report.found("Reported ROI differs from revenue vs spend") == 1
    assert "reported ROI mismatch" in df.loc[1, "quality_flag"]


def test_config_rejects_missing_columns(cfg, make_df):
    raw = make_df([make_row(1)]).drop(columns="rev")
    with pytest.raises(ConfigError):
        standardise_columns(raw, cfg)
    with pytest.raises(ConfigError):
        build_config({"columns": {"campaign": "id"}})
