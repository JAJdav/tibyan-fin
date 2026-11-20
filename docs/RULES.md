# Rules and Typologies (rules-v2)

Pattern taken from Tazama's rule-processor and typology-processor documentation, adapted to shop fraud and AML. Everything lives in `config/rules.json`; the engine is `app/rules/engine.py`.

## The idea in four lines

1. A **rule** looks at one feature and puts it in a **band** (`lower <= value < upper`) or a **case** (explicit list, or `ELSE`). It outputs only a **sub-rule reference**: `.00`, `.01`, `.02`, …
2. Two special references: `.x00` = **exit** (the rule could not be evaluated: missing data or cold start) and `.err` = the rule crashed.
3. A **typology** (a fraud or AML scenario) lists which rules it uses and a **weight per sub-rule reference**. The weights are **added** (capped at 100) and compared with two thresholds: `review` and `interdiction`.
4. Rules never carry weights. The same rule can feed several typologies with different weights.

> The `.x00` / `.err` naming follows my recollection of Tazama's convention; the documentation pages I could read did not spell it out. The mechanism (band/case → sub-rule ref → typology weight → thresholds) is documented there.

## Differences from Tazama (deliberate)

| Tazama | Here | Why |
|---|---|---|
| Rule runs a database query | Rule reads the feature snapshot | One consistent snapshot for rules, ML and graph; no extra latency |
| Weights live in typology (same) | Same | |
| Exit gives no contribution | Exit is reported as **not evaluated**; typology shows `complete: false` | "Could not check" must never look like "checked and clean" |
| Output goes to a typology/TADP chain | Output is the shared engine schema + `rule_action` | The later aggregator combines it with ML and graph |

`rule_action` (`none` / `review` / `interdiction`) is **not** the final decision. The decision engine comes later and also sees ML, graph and mandatory overrides.

## Shipped rules (all thresholds experimental)

| ID | Feature | Category | What it catches |
|---|---|---|---|
| R001 | `tx_count_5m` | fraud | Bursts of transactions |
| R002 | `tx_count_1h` | fraud | Sustained high hourly activity |
| R003 | `amount_zscore` | fraud | Amount far above the customer's own norm (exits on cold start) |
| R004 | `near_threshold_count_24h` | aml | Repeated amounts just below the reporting threshold |
| R005 | `is_new_device` | fraud | First use of a device (exits on cold start) |
| R006 | `secs_since_last_tx` | fraud | Transactions seconds apart |
| R007 | `country_code` | aml | Country on a list (**placeholder** XA/XB) |
| R008 | `distinct_devices_24h` | fraud | Many devices in a day |
| R009 | `sum_amount_24h` | aml | High daily volume |
| R010 | `hour_of_day_utc` | fraud | Night activity (UTC) |
| R011 | `amount` | fraud | Absolute value bands |
| R012 | `device_distinct_customers_24h` | aml | One device behind several customers (mule signal) |
| R013 | `channel` | fraud | Remote channels (weak signal, low weight) |
| R014 | `merchant_category` | aml | Watch-list categories (**placeholder** list) |

| Typology | Category | Rules | Review / interdiction |
|---|---|---|---|
| T001 Rapid-fire / card testing | fraud | R001 R002 R006 R013 | 40 / 80 |
| T002 Account takeover | fraud | R005 R003 R011 R008 R010 R013 | 50 / 85 |
| T003 Structuring | aml | R004 R009 R011 | 40 / 80 |
| T004 High-risk exposure | aml | R007 R014 R011 R009 | 50 / 90 |
| T005 Shared device / mule network | aml | R012 R005 R008 | 40 / 85 |

Example of why typologies matter: a 4,200 SAR transaction from a listed country scores only 40 on T004 (country alone), below review (50). A 12,000 SAR crypto transaction from that country scores 80 → `review`. Whether country alone should trigger review is a **policy choice for you**, and it is one number in the config.

## Output of the engine (inside `engines.rules`)

```json
{
  "engine": "rules", "status": "completed", "risk_score": 0.75, "rule_action": "review",
  "fraud_rule_score": 0.75, "aml_rule_score": 0.2, "coverage": 0.929,
  "reason_codes": ["AMOUNT_ANOMALY", "HIGH_VALUE", "NEW_DEVICE"],
  "rules": [ { "id": "R003@1.0.0", "cfg": "1.0.0", "subRuleRef": ".03", "status": "evaluated",
               "feature": "amount_zscore", "value": 41.2, "reason": "amount extremely above history",
               "reasonCode": "AMOUNT_ANOMALY", "flagged": true, "prcgTm": 0.002 } ],
  "typologies": [ { "id": "T002@1.0.0", "score": 75, "action": "review", "complete": true,
                    "contributions": [ { "rule_id": "R003", "subRuleRef": ".03", "wght": 35 } ],
                    "not_evaluated": [] } ]
}
```

`risk_score` = highest typology score / 100. It is a **lower bound** when `coverage < 1` (some rules exited).

## How to change behaviour

| I want to… | Edit |
|---|---|
| Change a threshold | The band's `lowerLimit` / `upperLimit` (keep bands contiguous) |
| Make a rule matter more | The weight in the typology's `wghts` |
| Make a typology stricter | Its `thresholds` |
| Add a rule on an existing feature | New entry in `rules`, then add it to a typology (`rules` and `expression`) |
| Rule needs a new signal | Add the feature in `features.py` (+ `FEATURE_SPECS`), then step above |
| Change the high-risk country / category lists | `cases[].values` of R007 / R014 |

The engine **refuses to start** with an invalid config (unknown feature, bands with gaps, weight for a non-existent sub-rule, expression not matching the rule list, review > interdiction). Run `pytest tests/test_rules.py` after edits.

## Limitations

- Weights and thresholds are guesses until calibrated on your labelled data (`docs/ANALYSIS.md`).
- Only the `Add` expression exists; no weighted average, no per-typology overrides, no exit-condition chaining between rules.
- Rule R013 fires on about a third of traffic in the synthetic set. Expect to lower its weight or change its cases once you see real channel mix.
- No "mandatory override" rules yet (sanctions-style hard blocks). Those belong to the decision engine stage.
