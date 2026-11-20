# Data Quality Report (M0 - generated)

Generated (UTC): 2026-11-20T09:51:59+00:00
Sampling cap: 300000 rows/file. Percentages describe **profiled rows only**.

## Dataset statistics

| File | MB | Rows profiled | Cols | Dup rows | Time span | Label positive rate |
|---|---|---|---|---|---|---|
| customers.csv | 1.35 | 6000 | 27 | 0 | 2010-12-31 00:00:00 -> 2026-04-20 00:00:00 | no label |
| devices.csv | 0.81 | 9921 | 11 | 0 | 2010-12-31 00:00:00 -> 2026-05-16 00:00:00 | no label |
| merchants.csv | 0.19 | 748 | 28 | 0 | 2014-12-03 00:00:00 -> 2026-01-31 00:00:00 | no label |


## Label distribution / imbalance

- **No label column detected.** Supervised fraud/AML training is not currently possible.

## Entity columns

- `customers.csv.customer_id`: 6000 unique, 0.0% null, 1.0 rows/entity
- `customers.csv.account_open_date`: 2768 unique, 0.0% null, 2.17 rows/entity
- `customers.csv.phone_hash`: 5994 unique, 0.0% null, 1.0 rows/entity
- `customers.csv.primary_device_id`: 6000 unique, 0.0% null, 1.0 rows/entity
- `customers.csv.card_hash_1`: 5987 unique, 0.0% null, 1.0 rows/entity
- `customers.csv.card_scheme_1`: 3 unique, 0.0% null, 2000.0 rows/entity
- `customers.csv.card_hash_2`: 2204 unique, 63.267% null, 2.72 rows/entity
- `customers.csv.card_scheme_2`: 2 unique, 63.267% null, 3000.0 rows/entity
- `devices.csv.device_id`: 9921 unique, 0.0% null, 1.0 rows/entity
- `devices.csv.device_kind`: 4 unique, 0.0% null, 2480.25 rows/entity
- `devices.csv.device_model`: 19 unique, 0.0% null, 522.16 rows/entity
- `merchants.csv.merchant_id`: 748 unique, 0.0% null, 1.0 rows/entity
- `merchants.csv.email_domain_type`: 2 unique, 0.0% null, 374.0 rows/entity
- `merchants.csv.phone_hash`: 748 unique, 0.0% null, 1.0 rows/entity
- `merchants.csv.console_device_id`: 748 unique, 0.0% null, 1.0 rows/entity

## Referential integrity

| Child | Parent | Orphan rows | Orphan % | Basis |
|---|---|---|---|---|
| customers.csv.phone_hash | merchants.csv.phone_hash | 5992 | 99.867 | profiled sample |


## Findings

| Severity | Table/Column | Check | Measured detail | Recommended action |
|---|---|---|---|---|
| HIGH | customers.csv | duplicate_key | id_type: 5997 repeated values (not unique) | Confirm grain: is this an entity FK or a transaction PK? Idempotency key depends on it. |
| HIGH | customers.csv | missing_values | gt_scenario_id: 5245 nulls (87.417%) | Explicit null policy + missingness indicator; never silent zero-fill. |
| HIGH | customers.csv | duplicate_key | gt_scenario_id: 5832 repeated values (not unique) | Confirm grain: is this an entity FK or a transaction PK? Idempotency key depends on it. |
| HIGH | customers.csv | missing_values | card_hash_2: 3796 nulls (63.267%) | Explicit null policy + missingness indicator; never silent zero-fill. |
| HIGH | customers.csv | missing_values | card_scheme_2: 3796 nulls (63.267%) | Explicit null policy + missingness indicator; never silent zero-fill. |
| HIGH | merchants.csv | future_timestamp | cr_expiry_date: 89 rows after current UTC time | Clock skew or synthetic data - blocks time-aware validation. |
| HIGH | merchants.csv | suspected_leakage_name | kyb_last_review_date matches post-event vocabulary | Verify availability at decision time; exclude unless provably pre-decision. |
| HIGH | merchants.csv | missing_values | gt_scenario_id: 700 nulls (93.583%) | Explicit null policy + missingness indicator; never silent zero-fill. |
| HIGH | merchants.csv | duplicate_key | gt_scenario_id: 700 repeated values (not unique) | Confirm grain: is this an entity FK or a transaction PK? Idempotency key depends on it. |
| HIGH | customers.csv.phone_hash | referential_integrity | 5992 orphans (99.867%) vs merchants.csv.phone_hash | Resolve FK mapping or restrict joins; document coverage. |
| MEDIUM | customers.csv | temporal_order | 2994 rows earlier than preceding row (file not time-sorted) | Sort by event time before time-based split and rolling features. |
| MEDIUM | devices.csv | temporal_order | 4896 rows earlier than preceding row (file not time-sorted) | Sort by event time before time-based split and rolling features. |
| MEDIUM | merchants.csv | temporal_order | 378 rows earlier than preceding row (file not time-sorted) | Sort by event time before time-based split and rolling features. |
| LOW | customers.csv | constant_column | residence_country has a single value | Drop from model features. |
| LOW | merchants.csv | constant_column | cr_status has a single value | Drop from model features. |
| INFO | customers.csv | profiled | 6000 rows x 27 cols; period: 2010-12-31 00:00:00 -> 2026-04-20 00:00:00 | Record in dataset stats. |
| INFO | devices.csv | profiled | 9921 rows x 11 cols; period: 2010-12-31 00:00:00 -> 2026-05-16 00:00:00 | Record in dataset stats. |
| INFO | merchants.csv | profiled | 748 rows x 28 cols; period: 2014-12-03 00:00:00 -> 2026-01-31 00:00:00 | Record in dataset stats. |


## Load errors

_none_


## Known limitations

- Results cover profiled rows only; re-run with a higher `--max-rows` for full-file guarantees.
- Leakage checks are **heuristics** (name patterns, single-column AUC); provenance must be confirmed by a human.
- Referential integrity is sample-based unless both tables were fully loaded.
- Business semantics, label definition, and data provenance are unknown until documented.

## Human decisions required before M1

- [ ] Confirm transaction grain and idempotency key.
- [ ] Confirm event-time column, timezone, and ordering guarantees.
- [ ] Confirm label definition(s): fraud vs AML, and observation window.
- [ ] Confirm which entity columns exist (device / merchant / account / counterparty).
- [ ] Approve dedup, null, negative-amount, and quarantine policies.
- [ ] Approve exclusion list for suspected leakage columns.
- [ ] Fill `Business meaning` in data_dictionary.md.