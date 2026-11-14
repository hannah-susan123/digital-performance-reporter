"""Runs the whole report on a small made-up CSV."""
import random

import pandas as pd
from openpyxl import load_workbook
from pptx import Presentation

import run_report
from reporter.insights import generate_insights
from reporter.pipeline import build_report
from tests.conftest import COLUMNS, make_row


def sample_csv(tmp_path):
    random.seed(1)
    rows = []
    for i in range(200):
        day = pd.Timestamp("2025-01-06") + pd.Timedelta(days=i % 56)
        rows.append(make_row(
            i, channel=random.choice(["Email", "SEO", "Paid Ads"]),
            seg=random.choice(["Youth", "Premium"]), conv=random.randint(5, 50),
            cpa=random.uniform(20, 80), rev=random.randint(500, 5000),
            day=f"{day:%Y-%m-%d}", days=random.randint(5, 30), platforms="Google, Email",
        ))
    path = tmp_path / "campaigns.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    cfg_path = tmp_path / "config.yaml"
    lines = ["columns:"] + [f"  {k}: {v}" for k, v in COLUMNS.items()] + ['date_format: "%Y-%m-%d"']
    cfg_path.write_text("\n".join(lines), encoding="utf-8")
    return path, cfg_path


def test_full_run_writes_excel_pptx_and_charts(tmp_path):
    csv, cfg = sample_csv(tmp_path)
    out = tmp_path / "out"
    assert run_report.main(["--input", str(csv), "--config", str(cfg), "--output", str(out)]) == 0

    xlsx = next(out.glob("report_*.xlsx"))
    sheets = load_workbook(xlsx).sheetnames
    for name in ["Summary", "By Channel", "By Segment", "By Campaign", "Weekly Trend"]:
        assert name in sheets
    slides = Presentation(next(out.glob("report_*.pptx"))).slides
    assert 6 <= len(slides) <= 8
    assert len(list((out / "charts").glob("*.png"))) >= 4


def test_close_groups_are_described_honestly(cfg):
    # two channels 1% apart should not be called a big win
    rows = [make_row(i, channel="Email", rev=1515) for i in range(5)]
    rows += [make_row(i + 5, channel="SEO", rev=1500) for i in range(5)]
    data = build_report(pd.DataFrame(rows), cfg)
    insights = generate_insights(data, cfg)
    assert "close" in insights.findings[0]
    assert "within" in insights.titles["channel"]


def test_missing_input_file_returns_error_code(tmp_path):
    assert run_report.main(["--input", str(tmp_path / "nope.csv")]) == 1
