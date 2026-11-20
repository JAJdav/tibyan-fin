"""Data quality profile -> reports/data_quality_report.md, reports/data_dictionary.md, reports/dataset_stats.json

  python scripts/profile_dataset.py                       # uses config/dataset_mapping.json
  python scripts/profile_dataset.py --file data/raw/my.csv

Everything reported is computed from the file. Nothing is assumed about the dataset.
"""
import argparse
import json
import re
from datetime import datetime, timezone

import pandas as pd

from _dataset import CANONICAL, REQUIRED, ROOT, load_mapping, read_raw, to_canonical

POST_EVENT_NAMES = re.compile(r"(fraud|chargeback|dispute|refund|reversal|status|review|label|flag|alert|sar|"
                              r"resolved|outcome|decline|block|case)", re.I)


def md_table(rows: list[list], header: list[str]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def auc(x: pd.Series, y: pd.Series) -> float | None:
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    pos, neg = (d["y"] == 1).sum(), (d["y"] == 0).sum()
    if pos == 0 or neg == 0:
        return None
    r = d["x"].rank()
    return float((r[d["y"] == 1].sum() - pos * (pos + 1) / 2) / (pos * neg))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--mapping")
    a = ap.parse_args()

    mapping = load_mapping(a.mapping)
    raw = read_raw(mapping, a.file)
    df, notes = to_canonical(raw, mapping)
    n = len(df)
    labelled = df["_label"].notna().any()
    stats: dict = {"rows": n, "raw_columns": list(raw.columns), "notes": notes}
    sections: list[str] = []
    problems: list[str] = []

    # ------------------------------------------------------------------ 1 structure + missing
    miss_rows = []
    for c in CANONICAL:
        m = int(df[c].isna().sum())
        miss_rows.append([c, "required" if c in REQUIRED else "optional", m, f"{m / n:.2%}"])
        if c in REQUIRED and m:
            problems.append(f"{m} rows have a missing required field `{c}`")
    sections.append("## 1. Missing values (canonical fields)\n" + md_table(miss_rows, ["field", "kind", "missing", "share"]))
    raw_miss = raw.isna().sum()
    stats["raw_missing"] = {k: int(v) for k, v in raw_miss[raw_miss > 0].items()}

    # ------------------------------------------------------------------ 2 duplicates
    full_dup = int(raw.duplicated().sum())
    id_dup = int(df["transaction_id"].duplicated().sum()) if df["transaction_id"].notna().any() else None
    conflicting = None
    if id_dup:
        g = raw.groupby(mapping["columns"]["transaction_id"]).nunique(dropna=False)
        conflicting = int((g.max(axis=1) > 1).sum())
    sections.append("## 2. Duplicates\n" + md_table(
        [["fully identical rows", full_dup], ["repeated transaction_id", id_dup],
         ["transaction_ids with conflicting content", conflicting]], ["check", "count"]))
    if full_dup:
        problems.append(f"{full_dup} fully duplicated rows")
    if conflicting:
        problems.append(f"{conflicting} transaction_ids appear with different content (idempotency conflict in production)")

    # ------------------------------------------------------------------ 3 invalid values
    bad_ts = int(df["timestamp"].isna().sum())
    bad_amount_nonnum = int(df["amount"].isna().sum())
    nonpos = int((df["amount"] <= 0).sum())
    now = pd.Timestamp(datetime.now(timezone.utc))
    future = int((df["timestamp"] > now).sum())
    cur_bad = int((~df["currency"].dropna().astype(str).str.fullmatch(r"[A-Za-z]{3}")).sum())
    cty_bad = int((~df["country"].dropna().astype(str).str.fullmatch(r"[A-Za-z]{2}")).sum())
    amt = df["amount"].dropna()
    sections.append("## 3. Invalid values\n" + md_table(
        [["unparseable timestamp", bad_ts], ["timestamp in the future", future],
         ["non-numeric / missing amount", bad_amount_nonnum], ["amount <= 0", nonpos],
         ["currency not 3 letters", cur_bad], ["country not 2 letters", cty_bad]], ["check", "rows"]))
    for label, cnt in [("unparseable timestamps", bad_ts), ("non-positive amounts", nonpos),
                       ("future timestamps", future)]:
        if cnt:
            problems.append(f"{cnt} rows with {label} (the API would reject these with HTTP 422)")
    if len(amt):
        q = amt.quantile([0.01, 0.5, 0.9, 0.99, 0.999])
        stats["amount_quantiles"] = {str(k): float(v) for k, v in q.items()}
        sections.append("Amount distribution (valid numbers): "
                        + ", ".join(f"p{float(k) * 100:g}={v:,.2f}" for k, v in q.items())
                        + f", max={amt.max():,.2f}")

    # ------------------------------------------------------------------ 4 label
    if labelled:
        lab = df["_label"].dropna().astype(int)
        pos = int(lab.sum())
        rate = pos / len(lab)
        stats["label"] = {"positives": pos, "labelled_rows": int(len(lab)), "rate": rate,
                          "unlabelled_rows": int(df["_label"].isna().sum())}
        lines = [f"- Labelled rows: {len(lab):,} (unlabelled: {int(df['_label'].isna().sum()):,})",
                 f"- Positives ({mapping['label'].get('name', 'label')}): {pos:,} = **{rate:.3%}**",
                 f"- Imbalance: about 1 positive per {int(round(1 / rate)) if rate else 'n/a'} rows"]
        if rate < 0.01:
            lines.append("- Severe imbalance: accuracy is meaningless here. Use precision, recall, PR-AUC, and "
                         "time-ordered splits.")
        if pos < 100:
            lines.append(f"- Only {pos} positives: metrics will be very noisy; avoid tuning many thresholds.")
        sections.append("## 4. Labels\n" + "\n".join(lines))
    else:
        sections.append("## 4. Labels\nNo usable label column. Supervised ML is not possible with this file; "
                        "only rules, anomaly detection and graph analysis apply.")

    # ------------------------------------------------------------------ 5 temporal
    t = df["timestamp"].dropna()
    tl = []
    if len(t):
        tl += [f"- Range: {t.min()} → {t.max()}  ({(t.max() - t.min()).days} days)",
               f"- Rows already in time order in the file: {'yes' if df['timestamp'].dropna().is_monotonic_increasing else 'no'}"
               " (the replay sorts them, which is what a time-aware split needs)"]
        per_day = t.dt.floor("D").value_counts().sort_index()
        tl.append(f"- Rows per day: min {per_day.min():,}, median {int(per_day.median()):,}, max {per_day.max():,};"
                  f" days with zero rows inside the range: {int((pd.date_range(per_day.index.min(), per_day.index.max(), freq='D').difference(per_day.index)).size)}")
        stats["time_range"] = [str(t.min()), str(t.max())]
        if labelled:
            m = df.dropna(subset=["timestamp", "_label"]).assign(month=lambda d: d["timestamp"].dt.strftime("%Y-%m"))
            mt = m.groupby("month")["_label"].agg(["count", "sum"])
            mt["rate"] = (mt["sum"] / mt["count"]).map("{:.3%}".format)
            tl.append("\nLabel rate by month (a fall in the most recent months can mean labels have not matured yet, "
                      "not that fraud fell):\n\n" + md_table(
                          [[i, int(r["count"]), int(r["sum"]), r["rate"]] for i, r in mt.iterrows()],
                          ["month", "rows", "positives", "rate"]))
    sections.append("## 5. Temporal consistency\n" + "\n".join(tl))

    # ------------------------------------------------------------------ 6 entities + referential integrity
    ent = []
    for c in ["customer_id", "account_id", "merchant_id", "device_id"]:
        if df[c].notna().any():
            ent.append([c, int(df[c].nunique()), f"{n / max(1, df[c].nunique()):.1f}"])
    sections.append("## 6. Entities\n" + md_table(ent, ["entity", "distinct", "avg rows per entity"]))
    ri = []
    if df["account_id"].notna().any() and df["customer_id"].notna().any():
        apc = df.groupby("account_id")["customer_id"].nunique()
        cpa = df.groupby("customer_id")["account_id"].nunique()
        ri += [["accounts linked to more than one customer", int((apc > 1).sum())],
               ["customers with more than one account", int((cpa > 1).sum())]]
        if (apc > 1).any():
            problems.append(f"{int((apc > 1).sum())} accounts are linked to more than one customer (check the key)")
    if df["device_id"].notna().any():
        dpc = df.dropna(subset=["device_id"]).groupby("device_id")["customer_id"].nunique()
        ri += [["devices used by more than one customer", int((dpc > 1).sum())],
               ["max customers on a single device", int(dpc.max())],
               ["rows with a missing device_id", int(df["device_id"].isna().sum())]]
        stats["shared_devices"] = int((dpc > 1).sum())
    if df["merchant_id"].notna().any():
        ri += [["merchants seen with only one customer", int((df.groupby("merchant_id")["customer_id"].nunique() == 1).sum())]]
    ri += [["rows whose customer_id has no other row", int((df["customer_id"].map(df["customer_id"].value_counts()) == 1).sum())]]
    sections.append("## 7. Referential / relationship checks\n" + md_table(ri, ["check", "count"])
                    + "\n\nOnly one transaction table was supplied, so integrity against separate customer/merchant "
                      "master tables could not be tested.")

    # ------------------------------------------------------------------ 8 leakage candidates
    leak = []
    label_col = (mapping.get("label") or {}).get("column")
    for c in raw.columns:
        if c == label_col:
            continue
        reasons = []
        if POST_EVENT_NAMES.search(str(c)):
            reasons.append("name suggests an outcome known only after the event")
        if labelled:
            y = df["_label"]
            s = raw[c]
            if s.dtype.kind in "if" and s.nunique() > 20:
                v = auc(s, y)
                if v is not None and (v > 0.95 or v < 0.05):
                    reasons.append(f"single-column AUC {v:.3f}")
            elif s.nunique() <= 50:
                d = pd.DataFrame({"x": s.astype(str), "y": y}).dropna()
                if len(d) and d["y"].nunique() == 2:
                    acc = d.groupby("x")["y"].agg(lambda z: max(z.mean(), 1 - z.mean()) * len(z)).sum() / len(d)
                    base = max(d["y"].mean(), 1 - d["y"].mean())
                    if acc > 0.995 and base < 0.995:
                        reasons.append(f"values almost perfectly determine the label ({acc:.3%} vs baseline {base:.3%})")
        if reasons:
            leak.append([c, "; ".join(reasons)])
    sections.append("## 8. Leakage candidates (heuristic, review manually)\n"
                    + (md_table(leak, ["column", "why"]) if leak else "None flagged by the heuristics. "
                       "This does not prove absence of leakage.")
                    + "\n\nAlso review any column that is only known after authorisation (settlement fields, "
                      "chargeback or review outcomes, post-event customer status). Features must exist at transaction time.")
    stats["leakage_candidates"] = [x[0] for x in leak]

    # ------------------------------------------------------------------ outputs
    head = ["# Data Quality Report", f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} from "
            f"`{a.file or mapping['file']}` ({n:,} rows).", ""]
    if notes:
        head += ["**Mapping notes**", *[f"- {x}" for x in notes], ""]
    summary = ["## Summary of problems found"] + ([f"- {p}" for p in problems] or ["- none of the automated checks fired"])
    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "data_quality_report.md").write_text("\n".join(head + summary) + "\n\n" + "\n\n".join(sections) + "\n", encoding="utf-8")
    (out_dir / "dataset_stats.json").write_text(json.dumps(stats, indent=2, default=str), encoding="utf-8")

    dd = ["# Data Dictionary (computed from the file)", "", "Descriptions are blank on purpose: fill them in, "
          "do not guess. Types and counts are measured.", ""]
    rows = []
    for c in raw.columns:
        s = raw[c]
        ex = ", ".join(str(v) for v in s.dropna().astype(str).unique()[:3])
        rows.append([c, str(s.dtype), f"{s.isna().mean():.2%}", s.nunique(dropna=True), ex[:60], ""])
    dd.append(md_table(rows, ["column", "dtype", "missing", "distinct", "examples", "meaning (you fill in)"]))
    (out_dir / "data_dictionary.md").write_text("\n".join(dd) + "\n", encoding="utf-8")

    print(f"{n:,} rows profiled. Problems found: {len(problems)}")
    for p in problems:
        print(" -", p)
    print(f"Reports written to {out_dir}")


if __name__ == "__main__":
    main()
