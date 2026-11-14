"""Load config.yaml and rename the dataset's columns to standard names."""
import copy

import pandas as pd
import yaml

STANDARD_FIELDS = [
    "campaign", "channel", "segment", "platform", "impressions", "clicks",
    "conversions", "conversion_rate", "spend", "cost_per_conversion",
    "revenue", "roi", "duration", "date",
]
REQUIRED = ["campaign", "channel", "impressions", "clicks", "revenue"]

DEFAULTS = {
    "date_format": None,
    "platform_separator": ",",
    "currency": "₹",
    "outlier_method": "log_iqr",
    "duration_bands": {
        "edges": [0, 7, 14, 21, float("inf")],
        "labels": ["1-7 days", "8-14 days", "15-21 days", "22+ days"],
    },
    "thresholds": {
        "week_change": 0.20,
        "partial_week_ratio": 0.5,
        "outlier_z": 3.0,
        "iqr_multiplier": 1.5,
        "similar_gap": 0.05,
        "roi_tolerance": 0.05,
    },
    "report": {"title": "Digital Campaign Performance Report", "top_n_campaigns": 25},
    "ai": {"model": "gemini-2.5-flash", "api_key_env": "GEMINI_API_KEY"},
}


class ConfigError(ValueError):
    pass


def load_config(path):
    with open(path, encoding="utf-8") as f:
        user_cfg = yaml.safe_load(f) or {}
    return build_config(user_cfg)


def build_config(user_cfg):
    """Merge user settings over the defaults and check the column mapping."""
    cfg = copy.deepcopy(DEFAULTS)
    for key, value in user_cfg.items():
        if isinstance(value, dict) and isinstance(cfg.get(key), dict):
            cfg[key].update(value)
        else:
            cfg[key] = value

    # drop blank mappings so "is this field available?" is just a key check
    columns = {k: v for k, v in (cfg.get("columns") or {}).items() if v}
    unknown = set(columns) - set(STANDARD_FIELDS)
    if unknown:
        raise ConfigError(f"Unknown fields in config columns: {sorted(unknown)}")
    missing = [f for f in REQUIRED if f not in columns]
    if missing:
        raise ConfigError(f"config.yaml must map these columns: {missing}")
    if "spend" not in columns and "cost_per_conversion" not in columns:
        raise ConfigError("Map either 'spend' or 'cost_per_conversion' in config.yaml")
    if "conversions" not in columns and "conversion_rate" not in columns:
        raise ConfigError("Map either 'conversions' or 'conversion_rate' in config.yaml")
    if cfg["outlier_method"] not in ("log_iqr", "iqr", "zscore"):
        raise ConfigError("outlier_method must be 'log_iqr', 'iqr' or 'zscore'")
    cfg["columns"] = columns
    return cfg


def standardise_columns(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """Keep only the mapped columns and rename them to standard names."""
    mapping = {source: std for std, source in cfg["columns"].items()}
    absent = [source for source in mapping if source not in df.columns]
    if absent:
        raise ConfigError(f"Columns named in config.yaml are not in the data: {absent}")
    return df[list(mapping)].rename(columns=mapping)
