"""Async intake: snapshot -> record -> graph.record -> parallel detection -> decision.

_provisional_decision() is a TEMPORARY M2 stub, replaced in M3.
"""
from __future__ import annotations
import asyncio, logging, time
from typing import Tuple

logger = logging.getLogger(__name__)

POLICY_VERSION = "provisional-m2"
WEIGHTS = {"rules": 0.35, "ml": 0.40, "graph": 0.25}     # unvalidated hypotheses
IDENTITY_KEYS = ("transaction_id", "customer_id", "account_id", "merchant_id", "device_id")


class IntakeService:
    def __init__(self, rules_engine, features, idem, metrics, orchestrator, specs, graph=None):
        self.rules = rules_engine
        self.features = features
        self.idem = idem
        self.metrics = metrics
        self.orchestrator = orchestrator
        self.specs = specs
        self.graph = graph                      # <-- must be passed from main.py

    def _resolve_writer(self):
        import inspect
        skip = {"get", "snapshot", "customer_count", "clear", "pop", "keys", "items", "values"}
        found = []
        for name in dir(self.idem):
            if name.startswith("_") or name in skip:
                continue
            fn = getattr(self.idem, name, None)
            if not callable(fn):
                continue
            try:
                sig = inspect.signature(fn)
            except (TypeError, ValueError):
                continue
            pos = [p for p in sig.parameters.values()
                   if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                   and p.default is p.empty]
            if len(pos) == 2:
                found.append((name, fn))
        if not found:
            raise AttributeError(
                "IdempotencyStore: no two-argument writer found. Methods available: "
                + ", ".join(n for n in dir(self.idem) if not n.startswith("_")))
        preferred = [f for n, f in found if n in ("put", "set", "store", "save", "remember", "add", "record")]
        fn = preferred[0] if preferred else found[0][1]
        logger.info("idempotency writer resolved to %s.%s", type(self.idem).__name__, fn.__name__)
        return fn

    def _remember(self, tx_id, body):
        if getattr(self, "_idem_write", None) is None:
            self._idem_write = self._resolve_writer()
        self._idem_write(tx_id, body)

    async def process(self, tx, correlation_id: str) -> Tuple[int, dict]:
        t0 = time.perf_counter()
        tx_id = tx.transaction_id

        stored = self.idem.get(tx_id)
        if stored is not None:
            self.metrics.inc("idempotent_replay")
            return 200, {**stored, "idempotent_replay": True}

        # 1-2. Leakage contract from features.py: snapshot is a pure read, record AFTER.
        snapshot = await asyncio.to_thread(self.features.snapshot, tx)
        await asyncio.to_thread(self.features.record, tx)

        # 3. Identities are NOT in the snapshot; engines need them.
        engine_input = {**snapshot,
                        **{k: getattr(tx, k) for k in IDENTITY_KEYS},
                        "timestamp": tx.timestamp.isoformat(),
                        "_tx": tx}

        # 4. Guaranteed graph state write, outside any engine timeout.
        if self.graph is not None:
            self.graph.record(engine_input)
        else:
            logger.warning("graph engine not wired into IntakeService; graph will be not_applicable")

        # 5. Scoring.
        results = await self.orchestrator.run(engine_input, correlation_id)
        summary = self.orchestrator.summary(results, self.specs)
        decision = self._provisional_decision(results, summary)
        ms = round((time.perf_counter() - t0) * 1000, 2)

        rr = next((r for r in results if r["engine"] == "rules"), {})
        body = {
            "transaction_id": tx_id, "correlation_id": correlation_id,
            "decision": decision["decision"], "risk_score": decision["risk_score"],
            "fraud_risk_score": decision["risk_score"],
            "aml_risk_score": rr.get("aml_rule_score"),
            "aml_status": "rules_only" if rr.get("aml_rule_score") is not None else "not_implemented",
            "rule_action": rr.get("rule_action"), "rules_coverage": rr.get("coverage"),
            "policy_version": POLICY_VERSION,
            "degraded": summary["degraded"], "engine_status": summary["engines"],
            "engine_results": results, "reason_codes": decision["reason_codes"],
            "model_versions": {r["engine"]: (r.get("model_version")
                                             or r.get("engine_version", "n/a")) for r in results},
            "feature_version": snapshot["feature_version"],
            "limitations": decision["limitations"], "processing_ms": ms,
        }
        self._remember(tx_id, body)
        self.metrics.inc(decision["decision"].lower())
        self.metrics.observe_ms(ms)
        return 200, body

    @staticmethod
    def _provisional_decision(results, summary):
        avail = [r for r in results if r["available"]]
        if not avail:
            return {"decision": "FLAG", "risk_score": None,
                    "reason_codes": ["ALL_ENGINES_UNAVAILABLE"],
                    "limitations": ["No engine produced a score; manual review required."]}
        wsum = sum(WEIGHTS.get(r["engine"], 0.0) for r in avail)
        score = sum(WEIGHTS.get(r["engine"], 0.0) * r["risk_score"] for r in avail) / wsum
        reasons = list(dict.fromkeys(rc for r in avail for rc in r["reason_codes"]))
        lim = []
        if summary["degraded"]:
            lim.append(f"Required engine(s) unavailable: {summary['unavailable_required']}. "
                       "Not treated as zero risk.")
            decision = "FLAG" if score < 0.75 else "HOLD"
        elif score > 0.75:
            decision = "HOLD"
        elif score >= 0.50:
            decision = "FLAG"
        else:
            decision = "APPROVE"
        lim.append("Weights/thresholds are unvalidated experimental hypotheses.")
        lim.append("Engine scores are not yet calibrated to a common scale.")
        return {"decision": decision, "risk_score": round(score, 4),
                "reason_codes": reasons, "limitations": lim}