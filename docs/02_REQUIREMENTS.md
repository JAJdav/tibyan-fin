# Requirements — Stage 1 (traceable)

Status legend: `PLANNED` → `IN_PROGRESS` → `DONE` (evidence link required).

## Functional

| ID | Requirement | Acceptance criterion | Milestone | Status |
|---|---|---|---|---|
| FR-01 | Repo + dataset inspection | `repo_inventory.md`, `data_quality_report.md`, `data_dictionary.md` generated from real data | M0 | PLANNED |
| FR-02 | Request validation | Invalid payload → 422 with field-level errors; no DB write | M1 | PLANNED |
| FR-03 | Idempotency | Same identity replayed → identical decision, exactly 1 `risk_decisions` row | M2 | PLANNED |
| FR-04 | Feature enrichment | Snapshot with `as_of`, `feature_version`, freshness, `missing_features` | M3 | PLANNED |
| FR-05 | Rules engine | Each rule returns id/name/triggered/severity/contribution/reasons/evidence; config-driven | M4 | PLANNED |
| FR-06 | ML detection | Versioned model, time-aware split, PR-AUC/recall/confusion matrix reported | M4 | PLANNED |
| FR-07 | Graph detection | Precomputed/incremental features; relationship evidence retained; no full rebuild per txn | M4 | PLANNED |
| FR-08 | Parallel orchestration | Engines run concurrently on one snapshot; per-engine timeout; error isolation | M5 | PLANNED |
| FR-09 | Shared result schema | Every engine emits `completed/failed/timeout/not_applicable` | M1/M5 | PLANNED |
| FR-10 | Risk aggregation | Normalized/calibrated inputs; separate fraud & AML scores; weights renormalized on missing engines | M5 | PLANNED |
| FR-11 | Deterministic decision | Same snapshot + policy version ⇒ identical decision (replay test) | M5 | PLANNED |
| FR-12 | Mandatory overrides | Override rules force minimum decision regardless of score | M5 | PLANNED |
| FR-13 | Durable persistence | No response returned before commit succeeds | M2 | PLANNED |
| FR-14 | Transactional outbox | Decision + investigation event committed atomically | M2 | PLANNED |
| FR-15 | Sync API | POST/GET transaction, GET investigation, /health, /metrics | M1–M6 | PLANNED |
| FR-16 | Async investigation | Worker consumes outbox; never blocks authorization | M6 | PLANNED |
| FR-17 | LLM report | Schema-valid JSON, evidence refs preserved, prompt+model version stored | M6 | PLANNED |
| FR-18 | LLM outage tolerance | Job stays pending/retried; authorization unaffected | M6 | PLANNED |
| FR-19 | Analytics pipeline | Batched Parquet + DuckDB marts; row counts reconcile with MySQL | M7 | PLANNED |
| FR-20 | Demonstration | End-to-end flagged txn → report retrievable by transaction id | M8 | PLANNED |

## Non-functional

| ID | Requirement | Target / policy | Verification |
|---|---|---|---|
| NFR-01 | Sync latency | Measure p50/p95/p99; **no claim without a reproducible run** | Locust/k6 report |
| NFR-02 | Throughput | Stage 1: measured baseline. 1,000 TPS = Stage 2 goal, unverified | benchmark report |
| NFR-03 | Decision deadline | `DECISION_DEADLINE_MS` (default 180) enforced; degrade, never hang | timeout test |
| NFR-04 | Durability | Commit before response; outbox recoverable after crash | kill-worker test |
| NFR-05 | Explainability | Every decision traceable to rule ids, model versions, graph evidence, policy version | replay test |
| NFR-06 | No fabricated risk | Missing/failed engine ≠ 0 risk; explicit degraded flag | failure-injection test |
| NFR-07 | LLM boundary | LLM never alters decision, never invents evidence | schema + reference validation |
| NFR-08 | Config-driven | Weights/thresholds/rules in versioned YAML, not code constants | policy version test |
| NFR-09 | Observability | Structured logs + correlation id on every hop; engine timing metrics | log inspection |
| NFR-10 | Data privacy | PII minimized in prompts/logs; secrets only in `.env` | review checklist |
| NFR-11 | Reproducibility | Pinned deps, dataset SHA256, model + policy + prompt versions recorded | artifact audit |

## Explicitly out of scope for Stage 1
Kafka, horizontal scaling, dedicated graph DB, distributed tracing, alerting, real payment-rail integration,
automated SAR filing, auto-blocking of real accounts.

## Open questions (blocked on M0 output)
1. Transaction grain + idempotency key? 2. Event-time column + timezone? 3. Fraud and/or AML labels present?
4. Device / merchant / counterparty columns present? 5. Dataset synthetic or real (affects claim wording)?
6. LLM provider + budget? 7. Hackathon time remaining?