# Feature Engineering Design (v1 — PROPOSED until M0 confirms columns)

**Every feature below is `status: proposed`.** A feature is promoted to `active` only when
`profile_dataset.py` confirms its source columns exist, are typed correctly, and are available at decision time.
Features whose columns are absent are marked `unavailable` and their rules return `not_applicable`.

## 1. Principles
1. **Point-in-time correctness** — a feature for transaction *t* uses only events with `event_time < t.event_time` (strict `<`, so the current transaction never leaks into its own history).
2. **Online/offline parity** — the same definition is computed in DuckDB/pandas (offline) and Redis (online); a parity test is a gate at M3.
3. **Explicit missingness** — absent feature ⇒ `null` + entry in `missing_features`. Never silent `0`.
4. **Freshness metadata** — every cached value carries `computed_at`; stale beyond `max_staleness` ⇒ treated as missing.
5. **Determinism & versioning** — `feature_version` is part of the decision record; changing a definition bumps the version.
6. **Cheap online, expensive offline** — O(1)/O(log n) reads in the request path; graph traversals and heavy aggregations precomputed asynchronously.

## 2. Feature snapshot contract (consumed identically by all engines)
```json
{
  "transaction_id": "TX10092",
  "correlation_id": "c-7f3a",
  "as_of": "2026-11-20T10:15:03.120Z",
  "feature_version": "fv1",
  "transaction": {"amount": 9500.0, "currency": "USD", "channel": "transfer", "direction": "out"},
  "entities": {"customer_id": "C1", "account_id": "A1", "device_id": null, "merchant_id": "M9"},
  "features": {"cust_txn_cnt_5m": 7, "cust_amt_z_30d": 4.2, "dev_accounts_24h": null},
  "missing_features": ["dev_accounts_24h"],
  "freshness": {"cust_txn_cnt_5m": {"computed_at": "...", "age_ms": 40, "source": "redis"}},
  "feature_status": "complete | partial | unavailable",
  "degraded": false
}
```

## 3. Feature catalog

`Req.` = required source columns (must be confirmed by M0). `Store` = online source.

### F1 Velocity (rules, ML, graph)
| ID | Feature | Window | Req. | Store |
|---|---|---|---|---|
| V1 | `cust_txn_cnt_{1m,5m,1h,24h}` | rolling | customer_id, event_time | Redis bucketed counter |
| V2 | `cust_amt_sum_{5m,1h,24h}` | rolling | + amount | Redis counter (float, cents) |
| V3 | `cust_distinct_merchants_1h` | rolling | + merchant_id | Redis HLL / set (bounded) |
| V4 | `cust_distinct_devices_24h` | rolling | + device_id | Redis set |
| V5 | `acct_in_out_cnt_1h` | rolling | account_id, direction | Redis counters |
| V6 | `seconds_since_last_txn` | last event | customer_id, event_time | Redis string |
| V7 | `burst_cnt_60s` | 60 s | customer_id, event_time | Redis ZSET |

### F2 Amount / behaviour deviation (rules, ML)
| ID | Feature | Window | Req. | Notes |
|---|---|---|---|---|
| A1 | `amt_zscore_cust_30d` | 30 d | amount, customer_id, time | expanding/rolling mean+std, **prior events only** |
| A2 | `amt_ratio_to_cust_median_30d` | 30 d | same | robust to outliers |
| A3 | `amt_percentile_merchant_30d` | 30 d | merchant_id | merchant-relative size |
| A4 | `is_round_amount` | instant | amount | configurable rounding granularity |
| A5 | `amt_vs_cust_max_7d` | 7 d | same | escalation signal |
| A6 | `first_seen_merchant` | lifetime | customer_id, merchant_id | Redis set / bloom |
| A7 | `first_seen_device` | lifetime | customer_id, device_id | conditional on column |

### F3 Temporal / channel (rules, ML)
`T1 hour_of_day`, `T2 is_night` (configurable, customer-local only if tz known), `T3 is_weekend`,
`T4 channel_change_vs_last`, `T5 new_geography` (only if geo columns exist), `T6 impossible_travel`
(only if geo + reliable timestamps; otherwise **not implemented**).

### F4 Merchant / counterparty (rules, ML, graph)
| ID | Feature | Req. | Leakage control |
|---|---|---|---|
| M1 | `merchant_fraud_rate_expanding` | merchant_id, label, time | **time-aware expanding window with Bayesian smoothing**; label matured (see §6) |
| M2 | `merchant_txn_cnt_1h` | merchant_id, time | prior events only |
| M3 | `merchant_distinct_customers_24h` | merchant_id, customer_id | cardinality burst |
| M4 | `counterparty_concentration_7d` | counterparty_id | share of volume to top-1 counterparty |

### F5 Graph (precomputed; graph engine + ML)
| ID | Feature | Req. | Computation |
|---|---|---|---|
| G1 | `device_account_degree_24h` | device_id, account_id | batch/incremental degree |
| G2 | `shared_device_flag` | device_id, customer_id | degree > configured threshold |
| G3 | `suspicious_neighbor_ratio_2hop` | labels or prior flags | **prior flags only**, never current labels |
| G4 | `fan_in_ratio_24h` / `fan_out_ratio_24h` | sender/receiver ids | in-degree vs out-degree |
| G5 | `component_size` | edges | periodic connected components |
| G6 | `cycle_participation_flag` | directed transfer edges | async cycle detection, cached flag |
| G7 | `days_since_edge_first_seen` | edge timestamps | relationship novelty |

Graph features are **precomputed and cached**; the synchronous path only reads them. Deep traversal belongs to
the asynchronous investigation worker.

### F6 AML patterns (rules; each is a configurable, auditable pattern — not a legal determination)
| ID | Pattern | Logic sketch | Req. |
|---|---|---|---|
| L1 | Structuring | ≥N cash-in events in window W, each `< T`, sum `≥ T` (T, N, W configurable) | amount, direction, channel, time, account |
| L2 | Rapid pass-through | `sum_out(0..Δ after credit) / credit ≥ r` with Δ small | direction, time, account |
| L3 | Funnel account | many distinct senders in W → concentrated out to few receivers | counterparty ids |
| L4 | Dormant-then-burst | inactivity ≥ D days, then count/amount ≥ k in W | account, time |
| L5 | Circular flow | directed cycle A→B→…→A within W | counterparty ids, time |
| L6 | Round-amount repetition | repeated near-identical amounts to same counterparty | amount, counterparty |
| L7 | Threshold proximity | amount within `[T·(1−ε), T)` repeatedly | amount, configured T |

Thresholds are **experimental configuration**, documented as hypotheses, never as validated regulatory thresholds.

## 4. Redis key design

| Key | Type | Op | TTL | Freshness |
|---|---|---|---|---|
| `f:{cust}:cnt:{bucket}` | HASH (per-minute fields) | `HINCRBY` + `EXPIRE` | window + slack | field timestamp = bucket |
| `f:{cust}:sum:{bucket}` | HASH (cents, int) | `HINCRBY` | window + slack | same |
| `f:{cust}:last_ts` | STRING | `SET` | 7 d | value is the timestamp |
| `f:{cust}:burst` | ZSET (score=ts) | `ZADD` + `ZREMRANGEBYSCORE` | 10 m | exact |
| `f:{cust}:merchants:{d}` | SET (bounded) | `SADD` | 24 h | approximate, capped |
| `g:{device}:accounts_24h` | STRING/INT | precomputed `SET` | 15 m | `computed_at` sidecar |
| `m:{merchant}:risk` | HASH | precomputed `HSET` | 1 h | `computed_at` + model version |

Design decisions:
- **Bucketed counters** (per-minute hash fields) for 1m/5m/1h/24h: O(1) writes, bounded memory, ±1 bucket precision.
- **ZSET sliding log** only for short exact windows (burst detection).
- Multi-key updates + freshness stamp executed in **one Lua script** ⇒ atomic per transaction.
- Amounts stored as **integer cents** to avoid float drift.
- `maxmemory-policy noeviction`; eviction of a counter would silently understate risk.

**Failure policy**

| Condition | Behaviour |
|---|---|
| Cache miss | bounded MySQL/DuckDB fallback query with its own time budget |
| Fallback exceeds budget | feature = `null`, added to `missing_features` |
| Redis unavailable | `feature_status=partial`, `degraded=true`; dependent rules → `not_applicable` |
| Critical features missing | policy forbids silent APPROVE; minimum decision = FLAG (configurable) |

## 5. Point-in-time computation (offline reference)
```python
# rolling aggregate EXCLUDING the current row
g = df.sort_values("event_time").groupby("customer_id")["amount"]
df["cust_amt_sum_1h"] = (
    g.rolling("1h", closed="left").sum().reset_index(level=0, drop=True)
)
```
For label-derived aggregates (e.g. merchant fraud rate) use an **expanding window with a maturity lag**:
only labels whose observation window has fully elapsed before `t` may contribute.

## 6. Leakage checklist (gate before any model training)
- [ ] No post-decision columns (chargeback, dispute, case, review, decision, alert, outcome).
- [ ] No column with single-column AUC ≥ 0.99 without documented provenance.
- [ ] Target/label encodings computed on **training folds only**, time-aware.
- [ ] Scalers/imputers fit on train only, inside the pipeline.
- [ ] Graph features built from edges with `edge_time < t`; no future edges.
- [ ] Duplicates removed **before** splitting.
- [ ] Time-based split (train < valid < test); group-aware split by customer to prevent identity memorization.
- [ ] Label maturity lag respected for any historical-rate feature.
- [ ] Every feature marked `available_at_decision_time = yes/no/unknown`; `unknown` ⇒ excluded.

## 7. Online/offline parity test (M3 gate)
Sample ≥1,000 historical transactions → compute features offline (DuckDB) and online (Redis replay) →
assert relative error ≤ 1% for counters/sums and exact match for flags; publish a mismatch table.
Any mismatch blocks M4.

## 8. Feature registry format (`config/features/registry.v1.yaml`, created at M3)
```yaml
feature_version: fv1
features:
  - id: V1
    name: cust_txn_cnt_5m
    dtype: int
    window: 5m
    source_columns: [customer_id, event_time]
    online: {store: redis, key: "f:{customer_id}:cnt:5m", op: bucketed_counter, ttl_s: 900}
    offline: {engine: duckdb, expr: "count(*) over prior 5m, closed=left"}
    consumers: [rules, ml]
    leakage_risk: low
    missing_policy: null_and_flag
    status: proposed        # proposed | active | unavailable
```