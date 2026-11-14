"""Build the weekly performance report from a campaign CSV.

    python run_report.py --input data/raw/nykaa_campaign_data.csv [--ai]
"""
import argparse
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

from reporter.ai_summary import write_summary
from reporter.charts import make_charts
from reporter.config import ConfigError, load_config
from reporter.excel_report import write_excel
from reporter.formatting import money, pct
from reporter.pipeline import build_report
from reporter.pptx_report import write_pptx


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Build the digital performance report.")
    parser.add_argument("--input", required=True, help="campaign CSV file")
    parser.add_argument("--config", default="config.yaml", help="column mapping and settings")
    parser.add_argument("--output", default="output", help="folder for the report files")
    parser.add_argument("--ai", action="store_true", help="add a Gemini executive summary")
    return parser.parse_args(argv)


def print_quality(quality):
    print(f"  {quality.rows_in:,} rows in, {quality.rows_out:,} rows out "
          f"({quality.rows_removed:,} removed)")
    issues = [c for c in quality.checks if c["found"]]
    if not issues:
        print(f"  All {len(quality.checks)} checks passed: no missing, duplicate or impossible values.")
    for c in issues:
        print(f"  - {c['check']}: {c['found']:,} ({c['action']})")


def main(argv=None):
    # Windows consoles default to a code page without ₹
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    started = time.time()

    try:
        cfg = load_config(args.config)
        print(f"[1/5] Reading {args.input}")
        raw = pd.read_csv(args.input)
        print("[2/5] Cleaning and checking data quality")
        data = build_report(raw, cfg, source=Path(args.input).name)
    except FileNotFoundError as exc:
        print(f"Error: file not found - {exc.filename}")
        return 1
    except (ConfigError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1

    cur = cfg["currency"]
    print_quality(data.quality)
    o = data.overall
    print(f"[3/5] KPIs: revenue {money(o['revenue'], cur)}, spend {money(o['spend'], cur)}, "
          f"ROAS {o['roas']:.2f}x, ROI {pct(o['roi'], 0)}, CTR {pct(o['ctr'], 2)}")
    if data.weekly is not None:
        print(f"  Weekly trend: {len(data.weekly)} weeks, {int(data.weekly['anomaly'].sum())} flagged")
    print(f"  Outlier campaigns ({cfg['outlier_method']}): {len(data.outliers):,}")

    print("[4/5] Findings")
    for i, finding in enumerate(data.insights.findings, 1):
        print(f"  {i}. {finding}")
    ai_summary = None
    if args.ai:
        print("  Asking Gemini for an executive summary...")
        ai_summary = write_summary(data, cfg)
        if ai_summary:
            print("\n  Executive summary:\n  " + ai_summary.replace("\n", "\n  ") + "\n")

    print("[5/5] Writing outputs")
    out = Path(args.output)
    stamp = date.today().isoformat()
    charts = make_charts(data, out / "charts", cfg)
    xlsx = write_excel(data, out / f"report_{stamp}.xlsx", cfg, ai_summary)
    pptx = write_pptx(data, charts, out / f"report_{stamp}.pptx", cfg, ai_summary)
    print(f"  Excel:      {xlsx}")
    print(f"  PowerPoint: {pptx}")
    print(f"  Charts:     {out / 'charts'} ({len(charts)} PNGs)")
    print(f"Done in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
