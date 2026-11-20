# Dataset Analysis Workflow

Run from the project root. Needs `pip install -r requirements-analysis.txt` (pandas, optional pyarrow).

## Step 0: describe your data

Put the file in `data/raw/` and edit `config/dataset_mapping.json`:

- `file`, `format` (`csv` or `parquet`)
- `columns`: our field names on the left, **your** column names on the right (`null` if you do not have it)
- `defaults` / `fill_from`: only for fields you lack (e.g. `account_id` copied from `customer_id`). The profile reports every such assumption
- `label`: your label column and which values mean "positive"
- `timestamp_unit`: `null` for text dates, `s` / `ms` for epoch numbers

## Step 1: profile

```powershell
python scripts\profile_dataset.py
```

Produces `reports/data_quality_report.md`, `reports/data_dictionary.md`, `reports/dataset_stats.json`:
missing values, duplicates (and conflicting duplicates), invalid values, label imbalance, label rate by month
(label maturity), temporal range and gaps, entity counts, accounts/devices shared across customers, and
heuristic **leakage candidates** (outcome-sounding column names; single columns that almost determine the label).

Leakage heuristics are a screen, not a proof. Review every column by asking "would I know this at authorisation time?"

## Step 2: replay through features and rules

```powershell
python scripts\replay_rules.py              # or --limit 50000 for a quick look
```

Sorts by time, then runs each row through the same `FeatureStore` and `RulesEngine` as the API (rows the API would reject
are skipped and counted; repeated `transaction_id`s skipped like the idempotency layer). Produces
`reports/rules_replay_report.md` and `data/processed/replay_features_rules.csv` (or `.parquet` if pyarrow is installed).

The report shows: action rates per 1,000 transactions (your analyst workload), firing and exit rate per rule, typology rates,
and, with labels, precision / recall / lift overall, per typology and per rule.

The processed table (all features + rule results, time-ordered, features computed point-in-time) is the **training table for the ML stage**.

## Step 3: tune without fooling yourself

1. Split by **time**, not at random: tune on the early period, judge on the later one.
2. Judge rules by **lift over the base rate** and by alerts per 1,000 transactions, not by accuracy.
3. A rule with high exit rate is silent for lack of data. Check `coverage` before concluding it is useless.
4. Positives that no rule catches are the target list for ML and graph work.
5. Change one thing at a time (a band edge, a weight, a threshold), re-run replay, compare reports. Keep the old reports.

## Try it without your data

```powershell
python scripts\make_synthetic.py
python scripts\profile_dataset.py
python scripts\replay_rules.py
```

The synthetic file has injected patterns and a few deliberate data problems (duplicates, negative amounts, missing country).
Its metrics prove the pipeline runs and **nothing else**; the report says so at the top.

## Known limits

- Replay speed is about 1,000 rows/s on a laptop-class machine (history scans are linear). Use `--limit` for big files.
- Only one transaction table is assumed, so referential integrity against master tables is not tested.
- No separate AML label is assumed; the single `label` is reported for both fraud and AML typologies. If your data has two
  labels, run the scripts twice with two mapping files (`--mapping`).
