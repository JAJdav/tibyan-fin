# M0 Data Inspection Plan

Every check below is executed by `scripts/profile_dataset.py` (or manually where noted).
Findings carry severity: **BLOCKER** (stops a dependent feature) / **HIGH** / **MEDIUM** / **LOW** / **INFO**.

| # | Check | Method | Artifact | Gates |
|---|---|---|---|---|
| 1 | Missing values | per-column null count/% | quality report | null policy, missingness indicators |
| 2 | Duplicate transactions | full-row dup + candidate-key dup | quality report | idempotency key, dedup policy |
| 3 | Invalid dtypes | numeric-parse rate on object cols | dictionary | ingestion casting/quarantine |
| 4 | Invalid amounts | negatives/zeros on amount-like cols | quality report | sign convention, direction field |
| 5 | Referential integrity | key-set membership across tables + `--fk` | quality report | join validity, graph edges |
| 6 | Label distribution | value counts on label candidates | quality report | supervised vs unsupervised |
| 7 | Class imbalance | positive rate, ratio | quality report | metrics choice, weighting |
| 8 | Temporal consistency | parse rate, min/max, future rows, out-of-order | quality report | time-aware split, velocity features |
| 9 | Data leakage (name) | post-event vocabulary match | quality report | exclusion list |
| 10 | Data leakage (signal) | single-column rank-AUC ≥0.99 vs label | quality report | exclusion list |
| 11 | Feature availability at t0 | **manual** provenance review per column | dictionary `Business meaning` | online feature eligibility |
| 12 | Entity consistency | cardinality, rows/entity, nulls | quality report | graph node types, aggregations |

## Contingency matrix — decide AFTER profiling (do not pre-commit)

| If the data lacks… | Then… |
|---|---|
| usable event timestamp | velocity/rolling/time features **disabled**; engines return `not_applicable`; no time-aware split; document as BLOCKER |
| `device_id` (or equivalent) | shared-device rule + graph pattern **not implemented** (never invented) |
| merchant/counterparty id | merchant-risk and fan-in/out features disabled; graph limited to available nodes |
| fraud labels | rules + unsupervised anomaly scoring only; report as heuristic, not calibrated probability |
| AML labels | AML score = rule/pattern-based only; explicitly labelled "no supervised AML model" |
| both labels | evaluation is qualitative + synthetic-injection, clearly marked as such |
| any positive class | supervised training blocked; state it plainly |
| realistic timestamps (all future/synthetic) | state dataset is synthetic; do not claim real-world performance |

## Outputs required to close M0
1. `data_quality_report.md` 2. `data_dictionary.md` (business meanings filled)
3. `dataset_profile.json` (stats + SHA256 fingerprints)
4. Known limitations section 5. Approved preprocessing strategy (dedup, nulls, casts, quarantine, exclusions, split)