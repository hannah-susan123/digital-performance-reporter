import pandas as pd
import pytest

from reporter.config import build_config

COLUMNS = {
    "campaign": "id", "channel": "type", "segment": "seg", "platform": "platforms",
    "impressions": "impr", "clicks": "clicks", "conversions": "conv",
    "cost_per_conversion": "cpa", "revenue": "rev", "roi": "roi",
    "duration": "days", "date": "day",
}


@pytest.fixture
def cfg():
    return build_config({"columns": dict(COLUMNS), "date_format": "%Y-%m-%d"})


def make_row(i, channel="Email", impr=1000, clicks=100, conv=10, cpa=50.0, rev=1500,
             seg="Youth", day="2025-01-06", days=10, platforms="Google"):
    spend = cpa * conv
    return {
        "id": f"C{i}", "type": channel, "seg": seg, "platforms": platforms,
        "impr": impr, "clicks": clicks, "conv": conv, "cpa": cpa, "rev": rev,
        "roi": round((rev - spend) / spend, 2) if spend else 0, "days": days, "day": day,
    }


@pytest.fixture
def make_df():
    def _make(rows):
        return pd.DataFrame(rows)
    return _make
