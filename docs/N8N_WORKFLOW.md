# n8n Workflow — Transaction Intake

File: `n8n/transaction_intake.workflow.json`

```
Webhook (POST /transaction)
   │
   ▼
Call FastAPI Intake  ── POST {FRAUD_API_URL}/api/v1/transactions   (3 tries, 10 s timeout,
   │                     X-Correlation-ID = n8n execution id        non-2xx passed through)
   ▼
Processed? ──no──► Route: error ───────────────┐
   │ yes                                       │
   ▼                                           │
Rule action review or higher? ─yes─► Route: needs_review ─┤
   └─no─► Route: clean ────────────────────────┤
                                               ▼
                                     Respond to Webhook
```

The workflow does **no detection itself**. All logic stays in the API; n8n only receives, calls, routes and responds. That keeps detection testable with `pytest` and independent of n8n.

Routing uses `engines.rules.rule_action` (`review` or `interdiction` → `needs_review`; `none` → `clean`). These are **routing labels**, not decisions. `clean` does not mean approved, because ML and graph are not active.

## Import and run

1. Start everything: `docker compose up -d --build`
2. Import: `docker compose exec n8n n8n import:workflow --input=/import/transaction_intake.workflow.json`
   (or in the UI: **Workflows → ⋯ → Import from file**)
3. Open http://localhost:5678, create the owner account on first visit, open the workflow.
4. **Test mode:** click **Execute workflow** (the webhook now listens once at `/webhook-test/transaction`), then:
   ```powershell
   python scripts\send_samples.py --url http://localhost:5678/webhook-test/transaction
   ```
   Test mode accepts one call per click of Execute.
5. **Production mode:** toggle the workflow **Active** and use `/webhook/transaction`:
   ```powershell
   python scripts\send_samples.py --url http://localhost:5678/webhook/transaction
   ```

## Expected results

| Scenario | `workflow_route` |
|---|---|
| `normal` | `clean` |
| `anomaly-new-device`, `burst-*` (the later ones) | `needs_review` |
| `structuring` (one near-threshold amount), `country-night` | `clean` (flagged reason codes, but no typology reached its review threshold; see `docs/RULES.md`) |
| `invalid` | `error` (API returns 422 with field errors) |
| Same id resent | same route, `idempotent_replay: true` |

(The first transactions of any new customer are cold start, so history-based rules will not fire yet. That is intended.)

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ECONNREFUSED` or "connection refused" in the HTTP node | Wrong host. Use `http://api:8000` inside compose, `http://host.docker.internal:8000` if the API runs on your PC, `http://localhost:8000` only if n8n runs on your PC |
| 404 on the webhook | Test URL used while workflow is not listening, or production URL used while inactive |
| `access to env vars denied` | Keep `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` (already in compose), or replace the URL expression with a literal URL |
| Everything returns `route: error` | Open the HTTP node output: look at `errors[]`. Usually a field name or timestamp format |
| Import complains about a node version | n8n versions differ. Create the node by hand in the UI with the same settings; the logic is the 8 nodes drawn above |

## Honest note

The workflow JSON was validated structurally (valid JSON, unique ids, every connection resolves) but **not executed inside a live n8n instance** in this environment. Import it once and run the sample script. If a node needs a small edit because of your n8n version, the diagram above is the specification.

## Where the later stages plug in

- After "Call FastAPI Intake": a branch for `HOLD`/`FLAG` that notifies an analyst (email, Slack, ticket).
- A second workflow polling `GET /api/v1/investigations/{id}` once the LLM stage exists.
- A scheduled workflow that triggers the Parquet/DuckDB export.
