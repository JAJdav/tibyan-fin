"""Central configuration. Everything tunable lives here or in config/rules.json."""
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

RULES_CONFIG_PATH = Path(os.getenv("RULES_CONFIG_PATH", BASE_DIR / "config" / "rules.json"))

FEATURE_VERSION = "features-v2"

# AML reporting threshold used by structuring features (your institution's value; 10,000 is a placeholder).
REPORTING_THRESHOLD = float(os.getenv("REPORTING_THRESHOLD", "10000"))
# "Near threshold" = amount in [REPORTING_THRESHOLD * (1 - band), REPORTING_THRESHOLD)
NEAR_THRESHOLD_BAND = float(os.getenv("NEAR_THRESHOLD_BAND", "0.10"))

# Cross-customer indexes (device, merchant) only need a short memory.
SHARED_INDEX_HOURS = int(os.getenv("SHARED_INDEX_HOURS", "48"))

# Reject transactions stamped further in the future than this (clock-skew tolerance).
MAX_FUTURE_SKEW_SECONDS = int(os.getenv("MAX_FUTURE_SKEW_SECONDS", "300"))

# Feature store limits (in-memory for this stage; Redis replaces it in a later stage).
HISTORY_DAYS = int(os.getenv("HISTORY_DAYS", "30"))
MAX_EVENTS_PER_CUSTOMER = int(os.getenv("MAX_EVENTS_PER_CUSTOMER", "5000"))

# Minimum prior transactions before amount statistics (mean/std/z-score) are trusted.
MIN_HISTORY_FOR_STATS = int(os.getenv("MIN_HISTORY_FOR_STATS", "5"))


def load_rules_config(path: Path | None = None) -> dict:
    with open(path or RULES_CONFIG_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)
