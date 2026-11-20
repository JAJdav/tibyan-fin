# Data Quality Report
Generated 2026-11-20 13:09 from `data/raw/synthetic_transactions.csv` (19,591 rows).

## Summary of problems found
- 10 fully duplicated rows
- 25 rows with non-positive amounts (the API would reject these with HTTP 422)

## 1. Missing values (canonical fields)
| field | kind | missing | share |
|---|---|---|---|
| transaction_id | required | 0 | 0.00% |
| customer_id | required | 0 | 0.00% |
| account_id | required | 0 | 0.00% |
| merchant_id | required | 0 | 0.00% |
| amount | required | 0 | 0.00% |
| currency | required | 0 | 0.00% |
| timestamp | required | 0 | 0.00% |
| device_id | optional | 0 | 0.00% |
| channel | optional | 0 | 0.00% |
| country | optional | 15 | 0.08% |
| merchant_category | optional | 0 | 0.00% |
| ip_address | optional | 19591 | 100.00% |

## 2. Duplicates
| check | count |
|---|---|
| fully identical rows | 10 |
| repeated transaction_id | 10 |
| transaction_ids with conflicting content | 0 |

## 3. Invalid values
| check | rows |
|---|---|
| unparseable timestamp | 0 |
| timestamp in the future | 0 |
| non-numeric / missing amount | 0 |
| amount <= 0 | 25 |
| currency not 3 letters | 0 |
| country not 2 letters | 0 |

Amount distribution (valid numbers): p1=12.00, p50=107.55, p90=341.27, p99=2,091.95, p99.9=9,800.50, max=12,000.00

## 4. Labels
- Labelled rows: 19,591 (unlabelled: 0)
- Positives (fraud): 581 = **2.966%**
- Imbalance: about 1 positive per 34 rows

## 5. Temporal consistency
- Range: 2026-08-01 08:06:03+00:00 → 2026-10-29 21:58:01+00:00  (89 days)
- Rows already in time order in the file: no (the replay sorts them, which is what a time-aware split needs)
- Rows per day: min 163, median 217, max 267; days with zero rows inside the range: 0

Label rate by month (a fall in the most recent months can mean labels have not matured yet, not that fraud fell):

| month | rows | positives | rate |
|---|---|---|---|
| 2026-08 | 6625 | 155 | 2.340% |
| 2026-09 | 6648 | 244 | 3.670% |
| 2026-10 | 6318 | 182 | 2.881% |

## 6. Entities
| entity | distinct | avg rows per entity |
|---|---|---|
| customer_id | 500 | 39.2 |
| account_id | 500 | 39.2 |
| merchant_id | 60 | 326.5 |
| device_id | 625 | 31.3 |

## 7. Referential / relationship checks
| check | count |
|---|---|
| accounts linked to more than one customer | 0 |
| customers with more than one account | 0 |
| devices used by more than one customer | 41 |
| max customers on a single device | 4 |
| rows with a missing device_id | 0 |
| merchants seen with only one customer | 0 |
| rows whose customer_id has no other row | 0 |

Only one transaction table was supplied, so integrity against separate customer/merchant master tables could not be tested.

## 8. Leakage candidates (heuristic, review manually)
None flagged by the heuristics. This does not prove absence of leakage.

Also review any column that is only known after authorisation (settlement fields, chargeback or review outcomes, post-event customer status). Features must exist at transaction time.
