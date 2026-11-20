"""Rule engine following the Tazama pattern, adapted to shop fraud / AML.

Pattern (from Tazama's rule-processor and typology-processor docs):
  * A RULE looks at ONE feature and classifies it into a band or a case. It emits only a
    sub-rule reference (".01", ".02", ...), never a score. Special refs: ".x00" = exit (rule could
    not be evaluated, e.g. missing data), ".err" = the rule crashed.
      - band : lowerLimit <= value < upperLimit      (null limit = unbounded)
      - case : value is in an explicit list, or ELSE
  * A TYPOLOGY maps (rule, subRuleRef) -> weight, combines the weights with an expression
    (only "Add" here), and compares the score to two thresholds: review and interdiction.

Differences from Tazama, on purpose:
  * rules read the feature snapshot (features.py) instead of querying a database;
  * a rule that exits or errors is reported as NOT EVALUATED, and the typology says it is
    incomplete. It is never silently counted as "no risk";
  * the typology score is capped at 100;
  * the engine's output uses this project's shared engine schema so the later aggregator and
    decision engine can consume it. Its `rule_action` is NOT the final decision.

Everything tunable lives in config/rules.json. validate_config() rejects a broken config at startup.
"""
import time
from typing import Any

from ..features import FEATURE_NAMES
from ..schemas import TransactionIn

EXIT_REF = ".x00"
ERROR_REF = ".err"
ACTION_ORDER = {"none": 0, "review": 1, "interdiction": 2}
SCORE_CAP = 100


class ConfigError(ValueError):
    pass


# ----------------------------------------------------------------------------- validation
def validate_config(cfg: dict, feature_names=FEATURE_NAMES) -> None:
    errors: list[str] = []
    rules = {}
    for r in cfg.get("rules", []):
        rid = r.get("id", "<missing id>")
        if rid in rules:
            errors.append(f"{rid}: duplicate rule id")
        rules[rid] = r
        if r.get("feature") not in feature_names:
            errors.append(f"{rid}: unknown feature {r.get('feature')!r}")
        has_b, has_c = "bands" in r, "cases" in r
        if has_b == has_c:
            errors.append(f"{rid}: define exactly one of 'bands' or 'cases'")
            continue
        refs = [x["subRuleRef"] for x in (r.get("bands") or r.get("cases"))]
        if len(refs) != len(set(refs)):
            errors.append(f"{rid}: duplicate subRuleRef")
        for ref in refs:
            if not ref.startswith(".") or ref in (EXIT_REF, ERROR_REF):
                errors.append(f"{rid}: invalid subRuleRef {ref!r}")
        if has_b:
            bands = r["bands"]
            if bands[0].get("lowerLimit") is not None or bands[-1].get("upperLimit") is not None:
                errors.append(f"{rid}: first band must have lowerLimit null and last band upperLimit null")
            for a, b in zip(bands, bands[1:]):
                if a.get("upperLimit") is None or a["upperLimit"] != b.get("lowerLimit"):
                    errors.append(f"{rid}: bands {a['subRuleRef']}->{b['subRuleRef']} are not contiguous")
        else:
            else_n = sum(1 for c in r["cases"] if c["values"] == "ELSE")
            if else_n > 1:
                errors.append(f"{rid}: more than one ELSE case")
        for ex in r.get("exit", []):
            if ex.get("feature") not in feature_names:
                errors.append(f"{rid}: exit condition uses unknown feature {ex.get('feature')!r}")

    seen_typ = set()
    for t in cfg.get("typologies", []):
        tid = t.get("id", "<missing id>")
        if tid in seen_typ:
            errors.append(f"{tid}: duplicate typology id")
        seen_typ.add(tid)
        members = {x["id"] for x in t.get("rules", [])}
        for x in t.get("rules", []):
            if x["id"] not in rules:
                errors.append(f"{tid}: references unknown rule {x['id']}")
                continue
            r = rules[x["id"]]
            valid = {c["subRuleRef"] for c in (r.get("bands") or r.get("cases") or [])}
            for w in x.get("wghts", []):
                if w["ref"] not in valid:
                    errors.append(f"{tid}: rule {x['id']} has no subRuleRef {w['ref']}")
                if not isinstance(w["wght"], (int, float)) or w["wght"] < 0:
                    errors.append(f"{tid}: weight for {x['id']}{w['ref']} must be a number >= 0")
        expr = t.get("expression", [])
        if not expr or expr[0] != "Add":
            errors.append(f"{tid}: only the 'Add' expression is supported")
        elif set(expr[1:]) != members:
            errors.append(f"{tid}: expression terms must equal the typology's rule list")
        th = t.get("thresholds", {})
        if not (0 < th.get("review", -1) <= th.get("interdiction", -1) <= SCORE_CAP):
            errors.append(f"{tid}: need 0 < review <= interdiction <= {SCORE_CAP}")
        if t.get("category") not in ("fraud", "aml"):
            errors.append(f"{tid}: category must be 'fraud' or 'aml'")
    if errors:
        raise ConfigError("invalid rules config:\n - " + "\n - ".join(errors))


# ----------------------------------------------------------------------------- classification
def _band(value: float, bands: list[dict]) -> dict | None:
    for b in bands:
        lo, hi = b.get("lowerLimit"), b.get("upperLimit")
        if (lo is None or value >= lo) and (hi is None or value < hi):
            return b
    return None


def _case(value: Any, cases: list[dict]) -> dict | None:
    else_case = None
    for c in cases:
        if c["values"] == "ELSE":
            else_case = c
        elif any((v is value) if isinstance(value, bool) else (v == value) for v in c["values"]):
            return c
    return else_case


def _exit_hit(ex: dict, features: dict) -> bool:
    v = features.get(ex["feature"])
    op = ex.get("op", "eq")
    if op == "is_null":
        return v is None
    if op == "eq":
        return v is ex["value"] if isinstance(ex["value"], bool) else v == ex["value"]
    raise ConfigError(f"unsupported exit operator {op!r}")


# ----------------------------------------------------------------------------- engine
class RulesEngine:
    def __init__(self, config: dict):
        validate_config(config)
        self.config = config
        self.version = config["version"]
        self.rules = {r["id"]: r for r in config["rules"]}
        self.typologies = config["typologies"]

    def _run_rule(self, rule: dict, features: dict) -> dict:
        start = time.perf_counter()
        base = {
            "id": f"{rule['id']}@{rule['version']}", "rule_id": rule["id"], "cfg": rule["cfg"],
            "name": rule["name"], "category": rule["category"], "feature": rule["feature"],
            "value": features.get(rule["feature"]),
        }
        try:
            hit, ref, reason, code, status = None, None, None, None, "evaluated"
            for ex in rule.get("exit", []):
                if _exit_hit(ex, features):
                    ref, reason, status = EXIT_REF, ex["reason"], "exit"
                    break
            if status == "evaluated" and base["value"] is None:
                ref, reason, status = EXIT_REF, f"feature '{rule['feature']}' is not available", "exit"
            if status == "evaluated":
                if "bands" in rule:
                    hit = _band(base["value"], rule["bands"])
                else:
                    hit = _case(base["value"], rule["cases"])
                if hit is None:
                    ref, reason, status = ERROR_REF, "value fell outside every band/case", "error"
                else:
                    ref, reason, code = hit["subRuleRef"], hit["reason"], hit.get("reasonCode")
        except Exception as exc:  # error isolation: one broken rule never kills the engine
            ref, reason, code, status = ERROR_REF, f"{type(exc).__name__}: {exc}", None, "error"
        return {**base, "subRuleRef": ref, "reason": reason, "reasonCode": code, "status": status,
                "flagged": status == "evaluated" and code is not None,
                "prcgTm": round((time.perf_counter() - start) * 1000, 4)}

    def _score_typology(self, t: dict, results: dict[str, dict]) -> dict:
        contributions, not_evaluated = [], []
        total = 0
        for member in t["rules"]:
            res = results[member["id"]]
            if res["status"] != "evaluated":
                not_evaluated.append({"rule_id": member["id"], "subRuleRef": res["subRuleRef"],
                                      "reason": res["reason"]})
                continue
            w = next((x["wght"] for x in member["wghts"] if x["ref"] == res["subRuleRef"]), 0)
            total += w
            contributions.append({"rule_id": member["id"], "subRuleRef": res["subRuleRef"], "wght": w})
        score = min(total, SCORE_CAP)
        th = t["thresholds"]
        action = "interdiction" if score >= th["interdiction"] else "review" if score >= th["review"] else "none"
        return {
            "id": f"{t['id']}@{t['version']}", "typology_id": t["id"], "name": t["name"],
            "category": t["category"], "score": score, "action": action, "thresholds": th,
            "complete": not not_evaluated, "contributions": contributions, "not_evaluated": not_evaluated,
        }

    def evaluate(self, tx: TransactionIn, features: dict) -> dict:
        start = time.perf_counter()
        results = {rid: self._run_rule(r, features) for rid, r in self.rules.items()}
        typologies = [self._score_typology(t, results) for t in self.typologies]

        evaluated = [r for r in results.values() if r["status"] == "evaluated"]
        errors = [{"rule_id": r["rule_id"], "error": r["reason"]} for r in results.values() if r["status"] == "error"]
        flagged = [r for r in evaluated if r["flagged"]]

        def best(cat=None):
            scores = [t["score"] for t in typologies if cat is None or t["category"] == cat]
            return round(max(scores, default=0) / SCORE_CAP, 4)

        action = max((t["action"] for t in typologies), key=ACTION_ORDER.get, default="none")
        return {
            "transaction_id": tx.transaction_id,
            "engine": "rules",
            "status": "failed" if not evaluated else "completed",
            # max typology score / 100. Lower bound when coverage < 1 (some rules exited).
            "risk_score": best(),
            "reason_codes": sorted({r["reasonCode"] for r in flagged}),
            "evidence": [{"rule_id": r["rule_id"], "subRuleRef": r["subRuleRef"], "feature": r["feature"],
                          "value": r["value"], "reason": r["reason"]} for r in flagged],
            "processing_ms": round((time.perf_counter() - start) * 1000, 3),
            "rules_version": self.version,
            "rule_action": action,
            "triggered_count": len(flagged),
            "fraud_rule_score": best("fraud"),
            "aml_rule_score": best("aml"),
            "coverage": round(len(evaluated) / len(results), 3),
            "rules": list(results.values()),
            "typologies": typologies,
            "errors": errors,
        }
