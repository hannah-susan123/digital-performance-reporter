"""Number formats and colours shared by the charts, Excel and PowerPoint."""
import math

# colours (hex without #)
BLUE = "2A78D6"      # highlight / the finding
GREY = "B8B6B0"      # everything else
RED = "E34948"       # weak performers and anomalies
INK = "0B0B0B"
INK_SOFT = "52514E"
SURFACE = "FCFCFB"
PANEL = "F1F0EC"
RED_FILL = "FBE3E3"
BLUE_FILL = "E3EEFA"


def is_missing(value):
    return value is None or (isinstance(value, float) and math.isnan(value))


def money(value, symbol="₹"):
    """Short money label in Indian units: ₹2,866.1 Cr, ₹4.6 L, ₹169."""
    if is_missing(value):
        return "n/a"
    sign = "-" if value < 0 else ""
    v = abs(value)
    if v >= 1e7:
        return f"{sign}{symbol}{v / 1e7:,.1f} Cr"
    if v >= 1e5:
        return f"{sign}{symbol}{v / 1e5:,.1f} L"
    return f"{sign}{symbol}{v:,.0f}"


def count(value):
    """Short count label: 306.0M, 52.0K, 812."""
    if is_missing(value):
        return "n/a"
    if abs(value) >= 1e9:
        return f"{value / 1e9:,.2f}bn"
    if abs(value) >= 1e6:
        return f"{value / 1e6:,.1f}M"
    if abs(value) >= 1e4:
        return f"{value / 1e3:,.1f}K"
    return f"{value:,.0f}"


def pct(value, decimals=1):
    return "n/a" if is_missing(value) else f"{value * 100:.{decimals}f}%"


def roas(value):
    return "n/a" if is_missing(value) else f"{value:.2f}x"


def excel_formats(symbol="₹"):
    """Header label and Excel number format for each standard column."""
    cur = f'"{symbol}"#,##0'
    return {
        "campaign": ("Campaign", None),
        "channel": ("Channel", None),
        "segment": ("Segment", None),
        "platform": ("Platform", None),
        "duration_band": ("Duration band", None),
        "duration": ("Duration (days)", "0"),
        "week": ("Week starting", "dd mmm yyyy"),
        "date": ("Date", "dd mmm yyyy"),
        "campaigns": ("Campaigns", "#,##0"),
        "impressions": ("Impressions", "#,##0"),
        "clicks": ("Clicks", "#,##0"),
        "conversions": ("Conversions", "#,##0"),
        "spend": (f"Spend ({symbol})", cur),
        "revenue": (f"Revenue ({symbol})", cur),
        "ctr": ("CTR", "0.00%"),
        "conversion_rate": ("Conversion rate", "0.00%"),
        "cpc": (f"Cost per click ({symbol})", cur + ".00"),
        "cost_per_conversion": (f"Cost per conversion ({symbol})", cur + ".00"),
        "roas": ("ROAS", '0.00"x"'),
        "roi": ("ROI", "0.0%"),
        "roas_vs_avg": ("ROAS vs average", "+0.0%;-0.0%;0.0%"),
        "revenue_change": ("Revenue WoW", "+0.0%;-0.0%;0.0%"),
        "roas_change": ("ROAS WoW", "+0.0%;-0.0%;0.0%"),
        "partial": ("Partial week", None),
        "anomaly": ("Anomaly", None),
        "note": ("Note", None),
        "reason": ("Why flagged", None),
        "return_score": ("Return score", "+0.0;-0.0;0"),
        "cost_score": ("Cost/conv score", "+0.0;-0.0;0"),
        "roas_lower_limit": ("Channel floor (ROAS)", '0.00"x"'),
        "loss": (f"Lost ({symbol})", cur),
        "outlier_type": ("Outlier type", None),
        "roi_reported": ("ROI (reported)", "0.00"),
        "quality_flag": ("Quality flag", None),
    }
