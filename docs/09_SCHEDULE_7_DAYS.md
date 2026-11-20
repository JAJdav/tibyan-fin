# 7-Day Execution Plan (Fri 20 Nov → Thu 26 Nov 2026)

Assumption: 1–2 builders. Every day ends with a committed report in `docs/PROGRESS.md`.
**Code freeze: Day 6, 20:00.** Day 7 is measurement + demo only.

| Day | Milestones | Concrete output | Gate (must pass to move on) |
|---|---|---|---|
| **1 — Fri 20** | M0 + M0.1 + M0.2 | discovery/profiling reports, provenance+license, docker up, `ollama pull`, LLM smoke test | Label question answered; feasibility matrix filled; smoke test prints VALID |
| **2 — Sat 21** | M1 + M2 | Pydantic contracts, config/logging, `/health`, MySQL DDL, idempotency, outbox | Duplicate POST ⇒ 1 row, identical response; commit-before-response proven |
| **3 — Sun 22** | M3 + rules | Redis rolling features, snapshot builder, 6–8 rules with unit tests | Online/offline parity ≤1% error; Redis-down degraded test passes |
| **4 — Mon 23** | M4 | Graph features (precomputed) + ML **only if labels exist** | Metrics report (PR-AUC/recall/CM) OR documented no-label path |
| **5 — Tue 24** | M5 + M6 | Parallel orchestrator, aggregator, policy v1, outbox worker + Qwen report | Flagged txn ⇒ report retrievable by id; LLM-outage test passes |
| **6 — Wed 25** | M7 + tests | Parquet batch writer, DuckDB marts, dashboard, integration + failure matrix | Mart counts reconcile with MySQL; demo run end-to-end twice |
| **7 — Thu 26** | M8 | Locust benchmark, architecture docs, demo rehearsal, buffer | Measured p50/p95/p99 published; no unverified claims |

## Cut lines (drop in this order if behind schedule)
1. **Power BI** → static HTML/Streamlit demo page reading the API. (Dashboard is a deliverable; the tool is not sacred.)
2. **Supervised ML** → if no labels: rules + IsolationForest, explicitly labelled heuristic. Never fake metrics.
3. **Graph cycle detection** → keep degree/shared-entity features only; drop cycles.
4. **k6/Locust 1,000 TPS** → publish the measured laptop baseline (likely 10² TPS) + the scaling path. This is honest and still scores.
5. **SAR draft** → keep the field, return `null`, document as future work.

Never cut: idempotency, durable persistence, outbox recovery, degraded-mode honesty, evidence traceability.

## Risk register
| Risk | Likelihood | Mitigation |
|---|---|---|
| No label column in the data | Medium | Day 1 discovery decides; rules+unsupervised path pre-planned |
| Local Qwen returns invalid JSON / hallucinated refs | Medium | Schema-constrained generation + reference resolution + repair retries + template fallback |
| VRAM insufficient / CPU-only inference slow | Medium | `qwen3:4b` fallback; async so latency is tolerable; measure on Day 1 |
| Dataset too large to profile/train | Medium | Sample with recorded SHA256 + row counts; stratified sampling; never claim full-data results |
| Known synthetic-dataset leakage columns | High if PaySim/IBM | Exclusion list decided Day 1 (e.g. `isFlaggedFraud` [[33]]) |
| Windows/Redis/Docker friction | Low | Redis in Docker, `noeviction`, verified Day 1 |
| Scope creep into Stage 2 | High | Kafka/horizontal scaling explicitly forbidden before Day 7 gate |

## Demo script (rehearse Day 6 and Day 7)
1. POST a normal transaction → APPROVE, show engine results + latency.
2. POST a burst of transactions from one account → velocity rule fires → FLAG/HOLD.
3. Replay the exact same transaction id → identical decision, `idempotent_replay: true`, still 1 DB row.
4. GET the investigation → Qwen report with traceable evidence refs.
5. Kill Ollama, POST another flagged txn → decision still returned instantly; job pending; restart Ollama → report appears.
6. Show DuckDB/Parquet mart + dashboard.
7. Show the measured benchmark table and state plainly what is and isn't verified.