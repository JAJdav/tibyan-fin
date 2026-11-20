# API Requests

Base URL: `http://localhost:8000`. All bodies are JSON. Header `X-Correlation-ID` is optional (generated if absent) and is echoed back.

## 1. Submit a transaction

`POST /api/v1/transactions`

| Field | Type | Required | Rules |
|---|---|---|---|
| `transaction_id` | string | yes | 1–64 chars of `A-Z a-z 0-9 _ - : .`. This is the idempotency key |
| `customer_id` | string | yes | same pattern |
| `account_id` | string | yes | same pattern |
| `merchant_id` | string | yes | same pattern |
| `amount` | number | yes | > 0 and ≤ 1,000,000,000 |
| `currency` | string | yes | 3 letters (ISO 4217), upper-cased automatically |
| `timestamp` | ISO 8601 | yes | Not more than 300 s in the future. No timezone means UTC |
| `device_id` | string | no | same pattern |
| `channel` | enum | no | `card_present`, `card_not_present`, `mobile`, `web`, `atm`, `wire`, `other` |
| `country` | string | no | 2 letters (ISO 3166) |
| `merchant_category` | string | no | ≤ 64 chars |
| `ip_address` | string | no | valid IPv4/IPv6 |

Unknown fields are **rejected** (HTTP 422), which catches typos in n8n field mappings.

### PowerShell

```powershell
$body = @{
  transaction_id = "TX10092"; customer_id = "C001"; account_id = "A001"; merchant_id = "M77"
  amount = 9500; currency = "SAR"; timestamp = (Get-Date).ToUniversalTime().ToString("o")
  device_id = "D9"; channel = "mobile"; country = "SA"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/transactions -ContentType "application/json" -Body $body
```

### curl (use `curl.exe` in PowerShell)

```bash
curl -X POST http://localhost:8000/api/v1/transactions \
  -H "Content-Type: application/json" \
  -d '{"transaction_id":"TX10092","customer_id":"C001","account_id":"A001","merchant_id":"M77",
       "amount":9500,"currency":"SAR","timestamp":"2026-11-20T09:30:00Z","device_id":"D9","country":"SA"}'
```

In PowerShell, `curl.exe` mangles inline JSON quotes. Prefer `Invoke-RestMethod` or `-d "@body.json"`.

### Success response (200), abridged

```json
{
  "status": "processed",
  "transaction_id": "TX10092",
  "correlation_id": "…",
  "idempotent_replay": false,
  "features": { "feature_version": "features-v2", "tx_count_5m": 1, "is_cold_start": true, "…": "…" },
  "engines": {
    "rules": {
      "engine": "rules", "status": "completed", "risk_score": 0.3, "rule_action": "none",
      "fraud_rule_score": 0.0, "aml_rule_score": 0.3, "coverage": 0.929, "triggered_count": 2,
      "reason_codes": ["HIGH_VALUE", "NEAR_THRESHOLD_AMOUNT"],
      "rules": ["... one result per rule: id, subRuleRef, status, feature, value, reason, reasonCode, flagged ..."],
      "typologies": ["... one per typology: score, action, complete, contributions, not_evaluated ..."],
      "errors": []
    },
    "ml":    { "engine": "ml",    "status": "not_applicable", "risk_score": null, "note": "not_implemented_in_this_stage" },
    "graph": { "engine": "graph", "status": "not_applicable", "risk_score": null, "note": "not_implemented_in_this_stage" }
  },
  "decision": null,
  "decision_note": "Risk aggregation and the decision engine are not part of this stage. …",
  "processing_ms": 0.4
}
```

`risk_score` of the stubbed engines is `null`, never `0`: "did not run" must never read as "no risk".

### Error responses

| HTTP | `status` | When |
|---|---|---|
| 422 | `rejected` | Validation failed. `errors[]` lists `{field, message}` |
| 409 | `conflict` | Same `transaction_id`, different payload |
| 409 | `in_progress` | Same `transaction_id` is still being processed. Retry shortly |
| 500 | – | Unexpected error. The id is released so the client may retry |

A rejected (422) transaction does **not** consume its `transaction_id`; you can fix it and resend.

### Idempotency behaviour

| You send | Result |
|---|---|
| New id | Processed, stored |
| Same id, same payload | Stored response returned with `idempotent_replay: true`. Nothing is recomputed or double-counted in history |
| Same id, different payload | 409 `conflict` |

## 2. Get a stored result

`GET /api/v1/transactions/{transaction_id}` → the stored response, or 404 `not_found`.

## 3. Other endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Status, versions, which engines are active |
| `GET /api/v1/rules` | The exact rule configuration currently loaded |
| `GET /api/v1/metrics` | In-process counters and p50/p95/p99 latency. **Not a benchmark** |
| `GET /docs` | Swagger UI |

## 4. Through n8n

`POST http://localhost:5678/webhook/transaction` (workflow active) or `/webhook-test/transaction` (while the editor is listening).
Same body. The response is the API response plus `workflow_route` (`needs_review`, `clean`, `error`) and `workflow_note`.

## Not built yet

`GET /api/v1/investigations/{transaction_id}` (needs the LLM stage). A decision field (`APPROVE/FLAG/HOLD`) (needs the aggregator).
