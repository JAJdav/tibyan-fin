# Interface Contracts (frozen at M1)

## Engine result (all three engines)
```json
{"transaction_id":"TX10092","engine":"graph","status":"completed","risk_score":0.87,
 "reason_codes":["SHARED_DEVICE"],"evidence":[],"processing_ms":12,
 "engine_version":"g1","degraded":false}
```
`status ∈ {completed, failed, timeout, not_applicable}`. Only `completed` contributes a score.
`failed`/`timeout` ⇒ weight renormalization + `degraded=true`; **never** coerced to 0.

## API
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/transactions` | validate → idempotency → features → engines → decision → persist → respond |
| GET | `/api/v1/transactions/{transaction_id}` | stored decision + engine results |
| GET | `/api/v1/investigations/{transaction_id}` | report or `202 pending` / `404 unknown` |
| GET | `/health` | liveness + dependency status |
| GET | `/metrics` | Prometheus exposition |

### POST response (minimum fields)
`transaction_id, decision (APPROVE|FLAG|HOLD), combined_risk_score, fraud_risk_score, aml_risk_score,
engine_results[], reason_codes[], model_versions{}, policy_version, feature_version,
degraded, missing_features[], correlation_id, processing_ms, idempotent_replay: bool`

## Decision policy (versioned YAML)
Weights `rules 0.35 / ml 0.40 / graph 0.25`; thresholds `<0.50 APPROVE`, `0.50–0.75 FLAG`, `>0.75 HOLD`
— **experimental hypotheses, not validated financial thresholds**. Mandatory overrides and
degraded-mode minimum decision are declared in the same file. Scores are normalized/calibrated before weighting.

## Investigation report
Schema exactly as specified in the master prompt §15, plus stored metadata:
`prompt_version, llm_model, llm_mode (live|mock), generated_at, evidence_refs[], retry_count`.
Validation: JSON schema + every `evidence[].reference` must resolve to a stored detection artifact.