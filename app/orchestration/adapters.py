"""Adapters binding existing engines to the async orchestrator contract."""
from __future__ import annotations
import asyncio
import time
from typing import Any, Dict

IDENTITY_KEYS = ("transaction_id", "customer_id", "account_id",
                 "merchant_id", "device_id", "timestamp", "_tx")
PASSTHROUGH = ("rule_action", "fraud_rule_score", "aml_rule_score", "coverage",
               "triggered_count", "rules_version", "typologies", "rules", "errors",
               "reason_codes", "evidence")


class RulesAdapter:
    """Binds the existing sync RulesEngine.evaluate(tx, features) to the async contract.

    The engine already emits the shared schema, so its payload is passed through
    rather than rebuilt. Identity keys and '_tx' are stripped so the engine receives
    exactly the feature snapshot it expects.
    """

    def __init__(self, engine):
        self.engine = engine
        self.version = getattr(engine, "version", "unknown")

    async def __call__(self, features: Dict[str, Any]):
        tx = features.get("_tx")
        if tx is None:
            raise RuntimeError("engine_input is missing '_tx'; RulesEngine needs the transaction")
        snapshot = {k: v for k, v in features.items() if k not in IDENTITY_KEYS}
        t0 = time.perf_counter()
        raw = await asyncio.to_thread(self.engine.evaluate, tx, snapshot)
        ms = round((time.perf_counter() - t0) * 1000, 3)

        out = {"transaction_id": raw.get("transaction_id", tx.transaction_id),
               "engine": "rules", "status": raw.get("status", "completed"),
               "risk_score": raw["risk_score"],
               "processing_ms": raw.get("processing_ms", ms),
               "engine_version": self.version}
        for k in PASSTHROUGH:
            if k in raw:
                out[k] = raw[k]
        out.setdefault("reason_codes", [])
        out.setdefault("evidence", [])
        return out


class UnavailableRules:
    """Stand-in when config/rules.json is absent. NEVER reports zero risk."""
    version = "unavailable"

    def __init__(self, reason: str):
        self.reason = reason

    async def __call__(self, features: Dict[str, Any]):
        return {"transaction_id": features.get("transaction_id", "UNKNOWN"),
                "engine": "rules", "status": "failed", "risk_score": None,
                "reason_codes": ["RULES_UNAVAILABLE"], "evidence": [],
                "error": self.reason, "engine_version": "unavailable"}