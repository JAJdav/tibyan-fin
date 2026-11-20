> **SYNTHETIC DATA.** The fraud patterns in this file were injected by `make_synthetic.py`, so the precision/recall below only prove the pipeline runs. They say nothing about real-world performance.
# Rules Replay Report
Generated 2026-11-20 13:10. Rules `rules-v2`, features `features-v2`.


## Volume
|  | rows |
|---|---|
| replayed | 19,556 |
| rejected by validation | 25 |
| repeated transaction_id skipped | 10 |

Rejection reasons:

| reason | rows |
|---|---|
| amount: Input should be greater than 0 | 25 |

## Rule actions (not final decisions)
| rule_action | rows | share | per 1,000 tx |
|---|---|---|---|
| none | 19095 | 97.64% | 976.4 |
| review | 406 | 2.08% | 20.8 |
| interdiction | 55 | 0.28% | 2.8 |

Mean rule coverage (share of rules that could be evaluated): **97.9%**; transactions in cold start: **13.1%**. Low coverage means history-based rules were silent for lack of data, not because the transaction looked safe.

## Per-rule firing rate
| rule | name | category | flagged | exit (.x00) | error |
|---|---|---|---|---|---|
| R001 | Velocity, 5 minutes | fraud | 0.64% | 0.0% | 0.0% |
| R002 | Velocity, 1 hour | fraud | 0.00% | 0.0% | 0.0% |
| R003 | Amount vs own history | fraud | 5.27% | 13.1% | 0.0% |
| R004 | Repeated near-threshold amounts | aml | 0.74% | 0.0% | 0.0% |
| R005 | New device | fraud | 1.21% | 13.1% | 0.0% |
| R006 | Rapid succession | fraud | 1.10% | 2.6% | 0.0% |
| R007 | High-risk country | aml | 0.00% | 0.1% | 0.0% |
| R008 | Many devices, 24 hours | fraud | 0.00% | 0.0% | 0.0% |
| R009 | Volume, 24 hours | aml | 0.30% | 0.0% | 0.0% |
| R010 | Night activity (UTC) | fraud | 0.21% | 0.0% | 0.0% |
| R011 | Transaction value | fraud | 1.51% | 0.0% | 0.0% |
| R012 | Shared device | aml | 0.63% | 0.0% | 0.0% |
| R013 | Card-not-present channel | fraud | 34.41% | 0.0% | 0.0% |
| R014 | High-risk merchant category | aml | 0.63% | 0.0% | 0.0% |

## Typologies
| typology | name | category | review or above | interdiction | max score |
|---|---|---|---|---|---|
| T001 | Rapid-fire / card testing | fraud | 0.64% | 0.00% | 65 |
| T002 | Account takeover | fraud | 1.08% | 0.07% | 100 |
| T003 | Structuring | aml | 0.52% | 0.21% | 80 |
| T004 | High-risk exposure | aml | 0.00% | 0.00% | 30 |
| T005 | Shared device / mule network | aml | 0.62% | 0.00% | 70 |

## Against labels (581 positives in 19,556 labelled rows, base rate 2.97%)

Overall, `rule_action` at review or above:

| flagged | TP | FP | FN | precision | recall | F1 | lift vs base rate |
|---|---|---|---|---|---|---|---|
| 461 | 441 | 20 | 140 | 95.7% | 75.9% | 84.6% | 32.2x |

Per typology (review or above):

| id | name | flagged | TP | precision | recall | lift |
|---|---|---|---|---|---|---|
| T001 | Rapid-fire / card testing | 126 | 126 | 100.0% | 21.7% | 33.7x |
| T002 | Account takeover | 211 | 211 | 100.0% | 36.3% | 33.7x |
| T003 | Structuring | 102 | 82 | 80.4% | 14.1% | 27.1x |
| T004 | High-risk exposure | 0 | 0 | n/a | 0.0% | n/a |
| T005 | Shared device / mule network | 122 | 122 | 100.0% | 21.0% | 33.7x |

Per rule (flagged):

| id | name | flagged | TP | precision | recall | lift |
|---|---|---|---|---|---|---|
| R001 | Velocity, 5 minutes | 126 | 126 | 100.0% | 21.7% | 33.7x |
| R002 | Velocity, 1 hour | 0 | 0 | n/a | 0.0% | n/a |
| R003 | Amount vs own history | 1030 | 289 | 28.1% | 49.7% | 9.4x |
| R004 | Repeated near-threshold amounts | 145 | 123 | 84.8% | 21.2% | 28.6x |
| R005 | New device | 237 | 237 | 100.0% | 40.8% | 33.7x |
| R006 | Rapid succession | 216 | 210 | 97.2% | 36.1% | 32.7x |
| R007 | High-risk country | 0 | 0 | n/a | 0.0% | n/a |
| R008 | Many devices, 24 hours | 0 | 0 | n/a | 0.0% | n/a |
| R009 | Volume, 24 hours | 59 | 42 | 71.2% | 7.2% | 24.0x |
| R010 | Night activity (UTC) | 42 | 42 | 100.0% | 7.2% | 33.7x |
| R011 | Transaction value | 296 | 296 | 100.0% | 50.9% | 33.7x |
| R012 | Shared device | 123 | 123 | 100.0% | 21.2% | 33.7x |
| R013 | Card-not-present channel | 6730 | 390 | 5.8% | 67.1% | 2.0x |
| R014 | High-risk merchant category | 123 | 123 | 100.0% | 21.2% | 33.7x |

**Read with care.** These numbers use thresholds that were never tuned on this data, but they are still in-sample for any later tuning. Compare rules against the base rate (lift), not against 100%. False negatives are the labelled positives no rule reached: study them, they are the ML and graph stages' job.

## Output
Full per-transaction features, rule results and typology scores: `data/processed/replay_features_rules.csv (install pyarrow for parquet)`.
