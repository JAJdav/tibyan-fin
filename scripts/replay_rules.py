"""Replay a historical dataset, in time order, through the SAME feature store and rules engine
the API uses. Produces a features+rules table (for later ML work) and a report.

  python scripts/replay_rules.py                 # uses config/dataset_mapping.json
  python scripts/replay_rules.py --file data/raw/my.csv --limit 50000

Notes
  * Rows the API would reject (HTTP 422) are skipped and counted, with the reason.
  * Repeated transaction_ids are skipped after the first, exactly like the idempotency layer.
  * Rules are NOT tuned on this data. Tuning thresholds on the full file and then reporting the same
    file's metrics would overstate quality; tune on an early period and judge on a later one.
"""
import argparse
from collections import Counter
from datetime import datetime

import pandas as pd
from pydantic import ValidationError

from _dataset import CANONICAL, ROOT, load_mapping, read_raw, to_canonical
from app.config import load_rules_config
from app.features import FeatureStore
from app.rules import RulesEngine
from app.schemas import TransactionIn

ACTION_RANK = {"none": 0, "review": 1, "interdiction": 2}


def md_table(rows, header):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def prf(flag: pd.Series, y: pd.Series) -> dict:
    tp = int((flag & (y == 1)).sum())
    fp = int((flag & (y == 0)).sum())
    fn = int((~flag & (y == 1)).sum())
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * r / (p + r) if p and r else None
    base = (y == 1).mean()
    return {"flagged": int(flag.sum()), "tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1,
            "lift": (p / base) if (p is not None and base) else None}


def fmt(v, pct=True, suffix=""):
    return "n/a" if v is None else (f"{v:.1%}" if pct else f"{v:.1f}{suffix}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    ap.add_argument("--mapping")
    ap.add_argument("--limit", type=int, help="replay only the first N valid rows in time order")
    a = ap.parse_args()

    mapping = load_mapping(a.mapping)
    df, notes = to_canonical(read_raw(mapping, a.file), mapping)
    labelled = df["_label"].notna().any()
    df = df.sort_values(["timestamp", "_row"], kind="stable", na_position="last").rename(columns={"_label": "label_y", "_row": "row_no"})

    store, engine = FeatureStore(), RulesEngine(load_rules_config())
    rejected: Counter = Counter()
    seen: set = set()
    out_rows: list[dict] = []
    skipped_dupes = 0

    for rec in df.itertuples(index=False):
        d = {c: (None if pd.isna(getattr(rec, c)) else getattr(rec, c)) for c in CANONICAL}
        if d["transaction_id"] in seen:
            skipped_dupes += 1
            continue
        try:
            tx = TransactionIn(**{k: v for k, v in d.items() if v is not None})
        except ValidationError as e:
            for err in e.errors():
                rejected[".".join(str(x) for x in err["loc"]) + ": " + err["msg"][:50]] += 1
            continue
        seen.add(tx.transaction_id)
        feats = store.snapshot(tx)
        res = engine.evaluate(tx, feats)
        store.record(tx)
        row = {"transaction_id": tx.transaction_id, "customer_id": tx.customer_id, "timestamp": tx.timestamp,
               "label": getattr(rec, "label_y"), **{k: v for k, v in feats.items() if k not in ("computed_at",)},
               "rules_risk_score": res["risk_score"], "rule_action": res["rule_action"],
               "rules_coverage": res["coverage"], "reason_codes": "|".join(res["reason_codes"])}
        for r in res["rules"]:
            row[f"{r['rule_id']}_ref"] = r["subRuleRef"]
            row[f"{r['rule_id']}_flagged"] = r["flagged"]
        for t in res["typologies"]:
            row[f"{t['typology_id']}_score"] = t["score"]
            row[f"{t['typology_id']}_action"] = t["action"]
        out_rows.append(row)
        if a.limit and len(out_rows) >= a.limit:
            break

    res_df = pd.DataFrame(out_rows)
    n = len(res_df)
    if n == 0:
        raise SystemExit("No valid rows to replay. See the rejection reasons: " + str(dict(rejected)))

    proc = ROOT / "data" / "processed"
    proc.mkdir(parents=True, exist_ok=True)
    try:
        res_df.to_parquet(proc / "replay_features_rules.parquet", index=False)
        out_file = "data/processed/replay_features_rules.parquet"
    except ImportError:
        res_df.to_csv(proc / "replay_features_rules.csv", index=False)
        out_file = "data/processed/replay_features_rules.csv (install pyarrow for parquet)"

    # ------------------------------------------------------------------ report
    act = res_df["rule_action"]
    synthetic = "synthetic" in str(a.file or mapping["file"]).lower()
    sec = [("> **SYNTHETIC DATA.** The fraud patterns in this file were injected by `make_synthetic.py`, so the "
            "precision/recall below only prove the pipeline runs. They say nothing about real-world performance.\n"
            if synthetic else "") + f"# Rules Replay Report\nGenerated {datetime.now().strftime('%Y-%m-%d %H:%M')}. "
           f"Rules `{engine.version}`, features `{res_df['feature_version'].iloc[0]}`.\n",
           "## Volume\n" + md_table([["replayed", f"{n:,}"], ["rejected by validation", f"{sum(rejected.values()):,}"],
                                     ["repeated transaction_id skipped", f"{skipped_dupes:,}"]], ["", "rows"])]
    if rejected:
        sec.append("Rejection reasons:\n\n" + md_table([[k, v] for k, v in rejected.most_common(10)], ["reason", "rows"]))
    sec.append("## Rule actions (not final decisions)\n" + md_table(
        [[k, int((act == k).sum()), f"{(act == k).mean():.2%}", f"{(act == k).mean() * 1000:.1f}"]
         for k in ("none", "review", "interdiction")], ["rule_action", "rows", "share", "per 1,000 tx"]))
    cold = res_df["is_cold_start"].mean()
    sec.append(f"Mean rule coverage (share of rules that could be evaluated): **{res_df['rules_coverage'].mean():.1%}**; "
               f"transactions in cold start: **{cold:.1%}**. Low coverage means history-based rules were silent for lack of data, "
               "not because the transaction looked safe.")

    rule_rows = []
    for rid, r in engine.rules.items():
        ref = res_df[f"{rid}_ref"]
        rule_rows.append([rid, r["name"], r["category"], f"{res_df[f'{rid}_flagged'].mean():.2%}",
                          f"{(ref == '.x00').mean():.1%}", f"{(ref == '.err').mean():.1%}"])
    sec.append("## Per-rule firing rate\n" + md_table(rule_rows, ["rule", "name", "category", "flagged", "exit (.x00)", "error"]))

    typ_rows = []
    for t in engine.typologies:
        a_ = res_df[f"{t['id']}_action"]
        typ_rows.append([t["id"], t["name"], t["category"], f"{(a_ != 'none').mean():.2%}",
                         f"{(a_ == 'interdiction').mean():.2%}", f"{res_df[f'{t['id']}_score'].max()}"])
    sec.append("## Typologies\n" + md_table(typ_rows, ["typology", "name", "category", "review or above", "interdiction", "max score"]))

    if labelled:
        lab = res_df.dropna(subset=["label"])
        y = lab["label"].astype(int)
        sec.append(f"## Against labels ({int(y.sum()):,} positives in {len(y):,} labelled rows, base rate {y.mean():.2%})")
        sec.append("Overall, `rule_action` at review or above:")
        m = prf(lab["rule_action"].map(ACTION_RANK) >= 1, y)
        sec.append(md_table([[m["flagged"], m["tp"], m["fp"], m["fn"], fmt(m["precision"]), fmt(m["recall"]),
                              fmt(m["f1"]), fmt(m["lift"], False, "x")]],
                            ["flagged", "TP", "FP", "FN", "precision", "recall", "F1", "lift vs base rate"]))
        rows_t = []
        for t in engine.typologies:
            mt = prf(lab[f"{t['id']}_action"].map(ACTION_RANK) >= 1, y)
            rows_t.append([t["id"], t["name"], mt["flagged"], mt["tp"], fmt(mt["precision"]), fmt(mt["recall"]),
                           fmt(mt["lift"], False, "x")])
        sec.append("Per typology (review or above):\n\n" + md_table(rows_t, ["id", "name", "flagged", "TP", "precision", "recall", "lift"]))
        rows_r = []
        for rid, r in engine.rules.items():
            mr = prf(lab[f"{rid}_flagged"].astype(bool), y)
            rows_r.append([rid, r["name"], mr["flagged"], mr["tp"], fmt(mr["precision"]), fmt(mr["recall"]), fmt(mr["lift"], False, "x")])
        sec.append("Per rule (flagged):\n\n" + md_table(rows_r, ["id", "name", "flagged", "TP", "precision", "recall", "lift"]))
        sec.append("**Read with care.** These numbers use thresholds that were never tuned on this data, but they are still "
                   "in-sample for any later tuning. Compare rules against the base rate (lift), not against 100%. "
                   "False negatives are the labelled positives no rule reached: study them, they are the ML and graph "
                   "stages' job.")
    else:
        sec.append("## Labels\nNo labels available, so no precision/recall. Only firing rates are shown.")

    sec.append(f"## Output\nFull per-transaction features, rule results and typology scores: `{out_file}`.")
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "rules_replay_report.md").write_text("\n\n".join(sec) + "\n", encoding="utf-8")
    print(f"Replayed {n:,} rows ({sum(rejected.values())} rejected, {skipped_dupes} repeated ids).")
    print(f"rule_action: " + ", ".join(f"{k}={int((act == k).sum())}" for k in ("none", "review", "interdiction")))
    print(f"Report: reports/rules_replay_report.md   Data: {out_file}")


if __name__ == "__main__":
    main()
