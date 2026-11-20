# Feature Engineering (features-v2)

Code: `app/features.py`. **`FEATURE_SPECS` in that file is the single source of truth**: name, type, scope, nullable, meaning.
The rule-config validator, the tests and the data dictionary all read it, and a test fails if the snapshot and the registry disagree.

## Principles (each one is tested)

1. **Point-in-time.** A snapshot uses only events with `timestamp <= current transaction`. A late-arriving older transaction cannot see later ones.
2. **No self-leakage.** The current transaction is recorded only after its snapshot is built. Velocity counts add the current transaction explicitly (`+1`).
3. **Never fabricate.** If a feature cannot be computed honestly it is `null`: z-score on cold start or zero variance, `is_new_device` with no `device_id`, `device_distinct_customers_24h` with no device.
4. **Cold start is explicit.** `is_cold_start` = fewer than 5 prior transactions. History-based rules **exit** instead of guessing.
5. **Versioned.** `feature_version` is in every response.

## State held (in memory for now; Redis later behind the same `snapshot()` / `record()` calls)

| Index | Key | Memory | Feeds |
|---|---|---|---|
| Customer history | `customer_id` | 30 days, max 5,000 events | velocity, behaviour, novelty, structuring |
| Device index | `device_id` → (time, customer) | 48 h | shared-device features; future graph edges |
| Merchant index | `merchant_id` → times | 48 h | merchant load |

## Catalogue (25 features)

| Group | Features |
|---|---|
| Transaction pass-through | `amount`, `country_code`, `channel`, `merchant_category` |
| State | `history_count`, `is_cold_start` |
| Velocity (incl. current) | `tx_count_5m`, `tx_count_1h`, `tx_count_24h`, `sum_amount_1h`, `sum_amount_24h`, `secs_since_last_tx` |
| Behaviour vs own history | `avg_amount_30d`, `std_amount_30d`, `amount_zscore`, `amount_to_avg_ratio` |
| Novelty | `is_new_merchant`, `is_new_device`, `is_new_country`, `distinct_devices_24h`, `distinct_merchants_24h` |
| AML shape | `amount_to_reporting_threshold`, `near_threshold_count_24h`, `is_round_amount` |
| Cross-entity | `device_distinct_customers_24h`, `merchant_tx_count_1h` |
| Calendar (UTC) | `hour_of_day_utc`, `day_of_week`, `is_weekend` |

Full definitions (and which can be null): `FEATURE_SPECS` in `app/features.py`.

`REPORTING_THRESHOLD` (default 10,000) and `NEAR_THRESHOLD_BAND` (default 10%) are set in `.env`. "Near threshold" is `[0.9 * T, T)`.

## Known limitations

- **One process, in memory.** History is lost on restart; no sharing across API instances. Redis with atomic rolling windows replaces it.
- **Linear window scans** per request (fine to a few thousand events per customer). Not tuned for 1,000 TPS and not claimed to be.
- **UTC hours.** "Night" in local time differs.
- **Merchant load is a raw count.** A busy merchant is not abnormal; it needs a per-merchant baseline, which needs real data.
- Statistics assume fairly stable behaviour and will misjudge legitimately bursty customers.
- **Features that need data you may not have:** account age, customer tenure, geo-distance/velocity, IP reputation. Decide after profiling.

## Adding a feature

1. Add the computation in `FeatureStore.snapshot()` and an entry in `FEATURE_SPECS`.
2. Add a test in `tests/test_features.py` (including the null and leakage cases).
3. Use it from `config/rules.json` and, later, as an ML column. The replay table will include it automatically.
