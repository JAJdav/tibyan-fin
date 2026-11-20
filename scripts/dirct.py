#!/usr/bin/env python3
"""
M0.1 - Data discovery. READ-ONLY. Finds data files anywhere under the root,
identifies label/time/entity columns, fingerprints known public synthetic datasets,
and emits a capability feasibility matrix.

    python scripts/discover_data.py --root . --out docs/reports
"""
from __future__ import annotations
import argparse, json, re, sqlite3, zipfile
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

SKIP = {".git", ".venv", "venv", "env", "__pycache__", "node_modules", ".pytest_cache",
        ".ruff_cache", ".mypy_cache", ".idea", ".vscode", "site-packages", "dist", "build",
        ".ipynb_checkpoints"}
DATA_EXT = {".csv", ".tsv", ".parquet", ".pq", ".json", ".jsonl", ".ndjson", ".xlsx", ".xls", ".feather"}
ARCH_EXT = {".zip", ".7z", ".gz", ".bz2", ".xz", ".tar", ".rar"}
DB_EXT = {".db", ".sqlite", ".sqlite3", ".duckdb"}

norm = lambda s: re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")

LABEL_HINT = re.compile(r"(^is_|fraud|launder|aml|suspicious|^label$|^target$|^class$|^y$)", re.I)
TIME_HINT = re.compile(r"(time|date|stamp|^ts$|_ts$|^step$|datetime)", re.I)
AMT_HINT = re.compile(r"(amount|amt|^value$|balance|price|total)", re.I)

# Capability -> column-name patterns that would satisfy it
CAPS = {
    "event_time":        [r"timestamp", r"^time$", r"transaction_?dt", r"^date", r"^step$", r"datetime"],
    "amount":            [r"amount", r"^amt", r"transaction_?amt", r"^value$"],
    "customer/user":     [r"customer", r"^user", r"name_?orig", r"client", r"^card\d?$"],
    "account":           [r"account", r"^acct", r"name_?dest", r"name_?orig"],
    "device":            [r"device", r"imei", r"id_\d\d", r"device_?info"],
    "merchant":          [r"merchant", r"mcc", r"product_?cd", r"payee"],
    "counterparty":      [r"name_?dest", r"to_?bank", r"receiver", r"beneficiary", r"recipient", r"^account_1$"],
    "bank/geo/channel":  [r"bank", r"country", r"addr", r"currency", r"payment_?format", r"^type$", r"channel"],
    "fraud_label":       [r"^is_?fraud$", r"^fraud$", r"^class$", r"^label$"],
    "aml_label":         [r"launder", r"^is_?aml$", r"^aml$"],
}

# Column-set fingerprints of widely used PUBLIC synthetic datasets.
# A match is a PROVENANCE HYPOTHESIS - the user must confirm the download source.
SIGNATURES = {
    "PaySim (mobile money, synthetic)": {
        "cols": {"step","type","amount","nameorig","oldbalanceorg","newbalanceorig","namedest",
                 "oldbalancedest","newbalancedest","isfraud","isflaggedfraud"},
        "label": "isFraud (fraud only, no AML label)",
        "caveats": ["`isFlaggedFraud` is a simulator rule output -> LEAKAGE, exclude [[33]]",
                    "balance columns are post-transaction state -> leakage risk [[35]]",
                    "`step` is hours, not a real timestamp; no device/merchant entities"],
    },
    "IBM AML (Kaggle, multi-agent synthetic)": {
        "cols": {"timestamp","from_bank","account","to_bank","account_1","amount_received",
                 "receiving_currency","amount_paid","payment_currency","payment_format","is_laundering"},
        "label": "Is Laundering (AML only, no fraud label)",
        "caveats": ["Fully synthetic multi-agent world; data under CDLA-Sharing-1.0 [[21]]",
                    "No customer/device/merchant identity -> graph is bank-account-to-account only",
                    "Extreme class imbalance; use PR-AUC/recall, never accuracy",
                    "Large variants exist -> sample before profiling/training"],
    },
    "IEEE-CIS fraud": {
        "cols": {"transactionid","transactiondt","transactionamt","productcd","card1","card4",
                 "addr1","p_emaildomain","r_emaildomain","isfraud"},
        "label": "isFraud (fraud only)",
        "caveats": ["TransactionDT is a relative time delta, not an absolute timestamp",
                    "identity file joins on TransactionID; many V/C/D columns are anonymized"],
    },
    "Kaggle creditcard (ULB)": {
        "cols": {"time","amount","class","v1","v2","v28"},
        "label": "Class (fraud only)",
        "caveats": ["V1..V28 are PCA components -> no interpretable entities, graph impossible",
                    "`Time` is seconds elapsed from first transaction"],
    },
}


def head(path: Path, n=2000):
    e = path.suffix.lower()
    if e in {".csv", ".tsv"}:
        df = pd.read_csv(path, nrows=n, low_memory=False)
        if df.shape[1] == 1:
            df = pd.read_csv(path, sep=None, engine="python", nrows=n)
        return df
    if e in {".parquet", ".pq"}:
        import pyarrow.parquet as pq
        return pq.ParquetFile(path).read_row_group(0).to_pandas().head(n)
    if e in {".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=True, nrows=n)
    if e == ".json":
        try:
            return pd.read_json(path, lines=True, nrows=n)
        except ValueError:
            return pd.read_json(path).head(n)
    if e in {".xlsx", ".xls"}:
        return pd.read_excel(path, nrows=n)
    if e == ".feather":
        return pd.read_feather(path).head(n)
    raise ValueError(e)


def fingerprint(cols):
    have = {norm(c) for c in cols}
    scored = []
    for name, sig in SIGNATURES.items():
        hit = len(have & sig["cols"]) / len(sig["cols"])
        scored.append((hit, name, sig))
    scored.sort(reverse=True, key=lambda x: x[0])
    hit, name, sig = scored[0]
    return ({"dataset_hypothesis": name, "match_score": round(hit, 2),
             "expected_label": sig["label"], "caveats": sig["caveats"]} if hit >= 0.6 else None)


def md_table(h, rows):
    if not rows:
        return "_none_\n"
    return "\n".join(["| " + " | ".join(h) + " |", "|" + "|".join(["---"] * len(h)) + "|"] +
                     ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in rows]) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="docs/reports")
    a = ap.parse_args()
    root, out = Path(a.root).resolve(), Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    found, archives, dbs, errors = [], [], [], []
    all_cols = {}

    for p in sorted(root.rglob("*")):
        if not p.is_file() or (set(p.parts) & SKIP):
            continue
        e = p.suffix.lower()
        rel = str(p.relative_to(root)).replace("\\", "/")
        if e in ARCH_EXT:
            inner = []
            if e == ".zip":
                try:
                    with zipfile.ZipFile(p) as z:
                        inner = [f"{i.filename} ({i.file_size/1e6:.1f} MB)" for i in z.infolist()[:20]]
                except Exception as exc:
                    inner = [f"<unreadable: {exc}>"]
            archives.append({"path": rel, "mb": round(p.stat().st_size / 1e6, 2), "contents": inner})
        elif e in DB_EXT:
            info = {"path": rel, "mb": round(p.stat().st_size / 1e6, 2), "tables": []}
            if e != ".duckdb":
                try:
                    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
                    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                        cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
                        n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                        info["tables"].append({"table": t, "rows": n, "columns": cols})
                        all_cols[f"{rel}:{t}"] = cols
                    con.close()
                except Exception as exc:
                    info["error"] = str(exc)
            dbs.append(info)
        elif e in DATA_EXT:
            try:
                df = head(p)
                cols = list(df.columns)
                all_cols[rel] = [str(c) for c in cols]
                labels = []
                for c in cols:
                    if LABEL_HINT.search(str(c)):
                        vc = df[c].value_counts(dropna=False).head(6).to_dict()
                        labels.append({"column": str(c), "sample_values": {str(k): int(v) for k, v in vc.items()}})
                found.append({
                    "path": rel, "mb": round(p.stat().st_size / 1e6, 2),
                    "columns": [str(c) for c in cols], "n_columns": len(cols),
                    "sample_rows": len(df),
                    "label_candidates": labels,
                    "time_candidates": [str(c) for c in cols if TIME_HINT.search(str(c))],
                    "amount_candidates": [str(c) for c in cols if AMT_HINT.search(str(c))],
                    "fingerprint": fingerprint(cols),
                    "sample_row": {str(k): str(v)[:40] for k, v in df.iloc[0].items()} if len(df) else {},
                })
            except Exception as exc:
                errors.append({"path": rel, "error": f"{type(exc).__name__}: {exc}"})

    # capability feasibility across ALL discovered tables
    flat = {norm(c) for cols in all_cols.values() for c in cols}
    matrix = []
    for cap, pats in CAPS.items():
        hits = sorted({c for c in flat for pat in pats if re.search(pat, c)})
        matrix.append({"capability": cap, "status": "YES" if hits else "NO",
                       "evidence_columns": ", ".join(hits[:6]) or "-"})

    result = {"generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "root": str(root), "data_files": found, "archives": archives,
              "databases": dbs, "read_errors": errors, "feasibility": matrix}
    (out / "data_discovery.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    md = ["# Data Discovery (M0.1)\n", f"Generated (UTC): {result['generated_at_utc']}",
          f"Root scanned: `{root}`\n",
          "## Capability feasibility (drives which engines/features are implementable)\n",
          md_table(["Capability", "Status", "Evidence columns"],
                   [[m["capability"], m["status"], m["evidence_columns"]] for m in matrix]),
          "\n## Data files\n",
          md_table(["Path", "MB", "Cols", "Label candidates", "Time candidates"],
                   [[f["path"], f["mb"], f["n_columns"],
                     ", ".join(l["column"] for l in f["label_candidates"]) or "NONE",
                     ", ".join(f["time_candidates"]) or "NONE"] for f in found])]
    for f in found:
        md.append(f"\n### `{f['path']}`\nColumns: {', '.join(f['columns'])}\n")
        if f["label_candidates"]:
            for l in f["label_candidates"]:
                md.append(f"- **Label candidate `{l['column']}`** — values in first {f['sample_rows']} rows: {l['sample_values']}")
        else:
            md.append("- **No label-like column found in this file.**")
        if f["fingerprint"]:
            fp = f["fingerprint"]
            md.append(f"- Provenance hypothesis: **{fp['dataset_hypothesis']}** (column match {fp['match_score']}) — CONFIRM manually")
            md.append(f"- Expected label: {fp['expected_label']}")
            md += [f"- Caveat: {c}" for c in fp["caveats"]]
    md += ["\n## Archives (extract before profiling)\n",
           md_table(["Path", "MB", "Contents"], [[x["path"], x["mb"], "; ".join(x["contents"])] for x in archives]),
           "\n## Database files\n",
           md_table(["Path", "MB", "Tables"],
                    [[d["path"], d["mb"], "; ".join(f"{t['table']}({t['rows']} rows)" for t in d["tables"]) or d.get("error", "n/a")] for d in dbs]),
           "\n## Read errors\n", md_table(["Path", "Error"], [[e["path"], e["error"]] for e in errors]),
           "\n## Next commands\n```powershell"]
    for f in found:
        md.append(f'python scripts/profile_dataset.py --input "{f["path"]}" --out docs/reports')
    md.append("```")
    (out / "data_discovery.md").write_text("\n".join(md), encoding="utf-8")

    print(f"[OK] {out/'data_discovery.md'}")
    for m in matrix:
        print(f"  {m['capability']:<20} {m['status']:<4} {m['evidence_columns']}")
    for f in found:
        labs = ", ".join(l["column"] for l in f["label_candidates"]) or "NONE"
        print(f"[FILE] {f['path']} ({f['mb']} MB, {f['n_columns']} cols) labels={labs}")


if __name__ == "__main__":
    main()