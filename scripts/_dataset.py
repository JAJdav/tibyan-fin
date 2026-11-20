"""Shared loading / column-mapping helpers for the analysis scripts."""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REQUIRED = ["transaction_id", "customer_id", "account_id", "merchant_id", "amount", "currency", "timestamp"]
OPTIONAL = ["device_id", "channel", "country", "merchant_category", "ip_address"]
CANONICAL = REQUIRED + OPTIONAL


def load_mapping(path: str | Path | None = None) -> dict:
    path = Path(path) if path else ROOT / "config" / "dataset_mapping.json"
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_raw(mapping: dict, file_override: str | None = None) -> pd.DataFrame:
    f = Path(file_override or mapping["file"])
    f = f if f.is_absolute() else ROOT / f
    if not f.exists():
        raise SystemExit(f"Dataset not found: {f}\nPut your file in data/raw/ and edit config/dataset_mapping.json")
    fmt = mapping.get("format", f.suffix.lstrip(".")).lower()
    if fmt == "parquet":
        return pd.read_parquet(f)
    return pd.read_csv(f, low_memory=False)


def to_canonical(raw: pd.DataFrame, mapping: dict) -> tuple[pd.DataFrame, list[str]]:
    """Returns (canonical dataframe, notes). Adds '_label' (0/1, NA if unlabeled) and '_row' (source row number)."""
    notes: list[str] = []
    out = pd.DataFrame(index=raw.index)
    cols = mapping["columns"]
    for name in CANONICAL:
        src = cols.get(name)
        if src and src in raw.columns:
            out[name] = raw[src]
        else:
            if src:
                notes.append(f"mapped column '{src}' for '{name}' not found in the file")
            out[name] = pd.NA
    for name, value in mapping.get("defaults", {}).items():
        if out[name].isna().all():
            out[name] = value
            notes.append(f"'{name}' absent: filled with constant {value!r}")
    for name, other in mapping.get("fill_from", {}).items():
        if out[name].isna().all():
            out[name] = out[other]
            notes.append(f"'{name}' absent: copied from '{other}' (assumes 1 account per customer)")

    unit = mapping.get("timestamp_unit")
    out["timestamp"] = (pd.to_datetime(out["timestamp"], unit=unit, utc=True, errors="coerce")
                        if unit else pd.to_datetime(out["timestamp"], utc=True, errors="coerce"))
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce")

    lab = mapping.get("label") or {}
    if lab.get("column") and lab["column"] in raw.columns:
        pos = {str(v).lower() for v in lab.get("positive_values", [1])}
        s = raw[lab["column"]]
        out["_label"] = s.map(lambda v: pd.NA if pd.isna(v) else int(str(v).lower() in pos)).astype("Int64")
    else:
        out["_label"] = pd.array([pd.NA] * len(out), dtype="Int64")
        if lab.get("column"):
            notes.append(f"label column '{lab['column']}' not found: running without labels")
    out["_row"] = range(len(out))
    return out, notes
