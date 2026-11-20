# Roadmap and Your Checklist

## What you do next

1. Unzip over `C:\Users\Analy\Desktop\hackthon\`, run the quick start, confirm `67 passed`.
2. **Point the project at your data**: file in `data/raw/`, edit `config/dataset_mapping.json`, run `profile_dataset.py` then `replay_rules.py` (`docs/ANALYSIS.md`). Send me (or read yourself) `reports/data_quality_report.md` and `rules_replay_report.md`.
3. Decide: reporting threshold, high-risk countries, watch-list merchant categories (placeholders today).
4. Send the **aml-compliance-system link** you meant (see below).

## Milestones

| # | Milestone | Depends on | Status |
|---|---|---|---|
| 1 | Feature engineering | – | Done |
| 2 | Rule engine (Tazama pattern) | 1 | Done |
| 3 | Dataset profile and rule replay tooling | 1, 2 | Done (run on your data) |
| 4 | Tune rules on a time split of your data | 3 + your data | Waiting on data |
| 5 | ML: fraud and AML models trained on the replay table | 3, 4 | Next |
| 6 | Real-time graph features | 1, 3 | Next |
| 7 | Aggregator and decision engine (weights, normalisation, overrides) | 2, 5, 6 | |
| 8 | MySQL, outbox, Redis state | 7 | |
| 9 | LLM investigation, DuckDB/Parquet, dashboard, benchmark | 8 | |

## ML plan (milestone 5)

- **Training table = `data/processed/replay_features_rules.*`**: features computed point-in-time, so there is no look-ahead.
- **Split by time** (e.g. train on the first 60% of days, validate next 20%, test last 20%). Never random.
- Baselines first: logistic regression, then XGBoost, optional isolation forest as an unsupervised signal.
- Metrics: PR-AUC, precision/recall at a fixed alert budget (alerts per 1,000), confusion matrix, error analysis. Not accuracy.
- Rule outputs (`sub-rule refs`, typology scores) may be features, but test the model **with and without** them to see if it adds signal beyond rules.
- Fraud and AML are trained separately **only if** your data has separate labels. One label means one model; do not invent AML labels.
- Blocked on: your labelled data, and how mature the labels are (the profile shows label rate by month).

## Real-time graph plan (milestone 6)

The reference repo you named (aml-compliance-system) did not come up in my search and the URL fetch was blocked, so this is a design from the requirements you gave, **not a port of that repo**. Send me the exact URL or its key files and I will align the patterns.

Batch graphs rebuild everything and then query. The real-time version must do the opposite:

1. **Maintain the graph incrementally.** On each transaction (after scoring) add or update edges: customer–device, customer–merchant, customer–account, and optionally customer→customer flows. Keep it as adjacency dictionaries with timestamps, pruned by a time window. The device index in `features.py` is already the first edge type.
2. **Score only a small neighbourhood, synchronously.** Look at 1–2 hops around the current customer/device: shared devices, number of distinct counterparties, whether neighbours were previously flagged. Bounded size, strict time budget, same shape as the other engines (`status`, `risk_score`, `reason_codes`, `evidence`).
3. **Move expensive analysis off the hot path.** Cycles (round-tripping), dense communities, layering chains and centrality run asynchronously on a snapshot, write back **precomputed per-node features** (e.g. `in_cycle`, `community_flag_rate`) that the synchronous scorer simply reads.
4. **Preserve evidence.** Every graph finding stores the path (which edges, which entities, when) so the investigation report can cite it.
5. NetworkX is fine for the demo. Only look at a graph database if measured evidence shows a limit.

What it needs from your data: reliable `device_id` and some entity link (account, beneficiary or counterparty). Without a counterparty column, only customer–device–merchant structures are possible; the profile reports what exists.

## Architectural decisions

| Decision | Problem | Choice | Alternative | Trade-off | Failure scenario | Later |
|---|---|---|---|---|---|---|
| Detection in the API, not in n8n | Logic in visual nodes is hard to test/version | n8n only orchestrates | Code nodes in n8n | One extra HTTP hop | API down → n8n retries 3×, then errors | Same pattern with Kafka/workers |
| Rules emit refs, typologies own weights | Reuse a rule in different scenarios with different importance | Tazama pattern | Weights inside rules | Two files to edit per change | Bad config → engine refuses to start (validator) | Versioned config in MySQL |
| Exit ≠ zero risk | Missing data must not look safe | `.x00` + `complete:false` + `coverage` | Treat as 0 | Scores are lower bounds on cold start | Many exits → low coverage visible in reports | Aggregator degraded-mode policy |
| Shared feature snapshot | Engines must agree on inputs | One `snapshot()` per transaction | Each engine reads its own data | Slight coupling | Missing feature → `null`, rule exits | Redis-backed snapshot |
| Feature registry (`FEATURE_SPECS`) | Names drift between code, rules, docs | Single source of truth + tests | Free strings | A little ceremony | Unknown feature in config → startup error | Generate data dictionary |
| Replay uses production code | Offline analysis must match online behaviour | Scripts import the same classes | Separate pandas logic | Slower than vectorised pandas | None: same code path | Training/serving parity for ML |
| In-memory state | No DB in this stage | Dicts behind small interfaces | Wait for MySQL/Redis | Lost on restart; one process | Restart → history gone | Redis + MySQL |

## Out of scope right now

ML models, graph engine, aggregator/decision engine, MySQL/Redis/DuckDB, LLM service, dashboard, load testing, Kafka.
