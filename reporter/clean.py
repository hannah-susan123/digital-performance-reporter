"""Data cleaning and quality checks."""
from dataclasses import dataclass, field

import pandas as pd

from .config import standardise_columns

TEXT_FIELDS = ["campaign", "channel", "segment", "platform"]
NUMERIC_FIELDS = [
    "impressions", "clicks", "conversions", "conversion_rate", "spend",
    "cost_per_conversion", "revenue", "roi", "duration",
]


@dataclass
class QualityReport:
    rows_in: int = 0
    rows_out: int = 0
    checks: list = field(default_factory=list)

    def log(self, check, found, action):
        found = int(found)
        self.checks.append({
            "check": check,
            "found": found,
            "action": action if found else "None found",
        })

    def found(self, check):
        """Count for a check, looked up by name (handy in tests)."""
        return next((c["found"] for c in self.checks if c["check"] == check), 0)

    @property
    def rows_removed(self):
        return self.rows_in - self.rows_out

    def as_frame(self):
        return pd.DataFrame(self.checks, columns=["check", "found", "action"])


def clean_data(raw: pd.DataFrame, cfg):
    """Return (clean dataframe, QualityReport)."""
    report = QualityReport(rows_in=len(raw))
    df = standardise_columns(raw, cfg)
    df["quality_flag"] = ""

    def drop(mask, check):
        report.log(check, mask.sum(), "Rows removed")
        return df[~mask]

    def flag(mask, check, note):
        report.log(check, mask.sum(), "Flagged, kept")
        df.loc[mask, "quality_flag"] = (df.loc[mask, "quality_flag"] + "; " + note).str.lstrip("; ")

    for col in TEXT_FIELDS:
        if col in df:
            text = df[col].astype("string").str.strip()
            blank = text.isna() | (text == "")
            report.log(f"Missing {col}", blank.sum(), "Filled with 'Unknown'")
            df[col] = text.mask(blank, "Unknown").astype(str)

    for col in NUMERIC_FIELDS:
        if col in df:
            numbers = pd.to_numeric(df[col], errors="coerce")
            report.log(f"Non-numeric {col}", (numbers.isna() & df[col].notna()).sum(), "Set to blank")
            df[col] = numbers

    # rows missing the numbers every KPI depends on can't be used
    core = ["impressions", "clicks", "revenue"]
    core.append("conversions" if "conversions" in df else "conversion_rate")
    core.append("spend" if "spend" in df else "cost_per_conversion")
    df = drop(df[core].isna().any(axis=1), "Missing core values")

    df = drop(df.drop(columns="quality_flag").duplicated(), "Duplicate rows")
    flag(df["campaign"].duplicated(keep=False), "Repeated campaign IDs", "repeated campaign ID")

    if "conversion_rate" in df:
        df = drop(~df["conversion_rate"].between(0, 100), "Conversion rate outside 0-100%")
    if "conversions" not in df:
        df["conversions"] = (df["clicks"] * df["conversion_rate"] / 100).round()
    if "spend" not in df:
        df["spend"] = df["cost_per_conversion"] * df["conversions"]

    for col in ["impressions", "clicks", "conversions", "spend", "revenue"]:
        df = drop(df[col] < 0, f"Negative {col}")
    df = drop(df["clicks"] > df["impressions"], "Clicks greater than impressions")
    df = drop(df["conversions"] > df["clicks"], "Conversions greater than clicks")
    flag(df["spend"] == 0, "Zero spend", "zero spend, ROAS not calculable")

    if "date" in df:
        parsed = pd.to_datetime(df["date"], format=cfg.get("date_format"), errors="coerce")
        report.log("Unreadable dates", parsed.isna().sum(), "Kept, left out of weekly trend")
        df["date"] = parsed

    if "roi" in df:
        # keep the reported figure for reference; the report uses its own ROI
        df = df.rename(columns={"roi": "roi_reported"})
        calculated = (df["revenue"] - df["spend"]) / df["spend"].where(df["spend"] != 0)
        mismatch = (calculated - df["roi_reported"]).abs() > cfg["thresholds"]["roi_tolerance"]
        flag(mismatch, "Reported ROI differs from revenue vs spend", "reported ROI mismatch")

    report.rows_out = len(df)
    return df.reset_index(drop=True), report
