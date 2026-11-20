"""M2 — Parallel detection orchestrator.

Contract: every engine returns the shared result schema. Unavailable engines
return risk_score=None (never 0.0) so the aggregator cannot silently approve.
Python 3.10 compatible (asyncio.wait_for, not asyncio.timeout).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

EngineFn = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]

COMPLETED = "completed"
FAILED = "failed"
TIMEOUT = "timeout"
NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class EngineSpec:
    name: str
    fn: EngineFn
    timeout_s: float
    required: bool = True          # required engine missing => degraded mode

PRESERVE = ("model_version", "engine_version", "details", "rule_action",
            "fraud_rule_score", "aml_rule_score", "coverage", "complete", "typologies")
def _unavailable(tx_id, engine, status, detail, correlation_id, processing_ms=0.0):
    return {
        "transaction_id": tx_id,
        "engine": engine,
        "status": status,
        "risk_score": None,                 # NOT zero risk
        "available": False,
        "reason_codes": [f"{engine.upper()}_{status.upper()}"],
        "evidence": [],
        "error": detail,
        "processing_ms": round(processing_ms, 2),
        "correlation_id": correlation_id,
    }


def _normalize(res, tx_id, name, correlation_id, elapsed_ms):
    status = res.get("status", COMPLETED)
    score = res.get("risk_score")

    if status == COMPLETED:
        if not isinstance(score, (int, float)):
            return _unavailable(tx_id, name, FAILED,
                                "engine returned non-numeric risk_score",
                                correlation_id, elapsed_ms)
        score = max(0.0, min(1.0, float(score)))
    else:
        score = None

    out = {
        "transaction_id": res.get("transaction_id") or tx_id,
        "engine": name,
        "status": status,
        "risk_score": score,
        "available": status == COMPLETED,
        "reason_codes": list(res.get("reason_codes") or []),
        "evidence": list(res.get("evidence") or []),
        "processing_ms": round(float(res.get("processing_ms") or elapsed_ms), 2),
        "correlation_id": correlation_id,
    }
    for key in ("model_version", "engine_version", "details"):
        if key in res:
            out[key] = res[key]
    return out


class DetectionOrchestrator:
    def __init__(
        self,
        specs: List[EngineSpec],
        overall_deadline_s: float = 0.25,
        max_concurrency: int = 64,
    ):
        self._specs = specs
        self._deadline_s = overall_deadline_s
        self._max_concurrency = max_concurrency
        self._sem: Optional[asyncio.Semaphore] = None   # lazy: must bind to running loop

    def _semaphore(self) -> asyncio.Semaphore:
        if self._sem is None:
            self._sem = asyncio.Semaphore(self._max_concurrency)
        return self._sem

    async def run(self, features: Dict[str, Any], correlation_id: str | None = None):
        tx_id = str(features.get("transaction_id", "UNKNOWN"))
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._deadline_s
        sem = self._semaphore()

        results = await asyncio.gather(
            *(self._run_one(s, features, tx_id, correlation_id, loop, deadline, sem)
              for s in self._specs),
            return_exceptions=True,
        )

        final = []
        for spec, res in zip(self._specs, results):
            if isinstance(res, BaseException):
                logger.error("engine=%s tx=%s cid=%s crashed", spec.name, tx_id,
                             correlation_id, exc_info=res)
                final.append(_unavailable(tx_id, spec.name, FAILED,
                                          f"{type(res).__name__}: {res}", correlation_id))
            else:
                final.append(res)
        return final

    async def _run_one(self, spec, features, tx_id, cid, loop, deadline, sem):
        budget = min(spec.timeout_s, max(0.0, deadline - loop.time()))
        if budget <= 0:
            return _unavailable(tx_id, spec.name, TIMEOUT,
                                "overall deadline exhausted before dispatch", cid)

        t0 = time.perf_counter()

        async def _call():
            async with sem:                 # queueing counts against the budget
                return await spec.fn(features)

        try:
            raw = await asyncio.wait_for(_call(), timeout=budget)
        except asyncio.TimeoutError:
            ms = (time.perf_counter() - t0) * 1000
            logger.warning("engine=%s tx=%s cid=%s timeout budget=%.3fs",
                           spec.name, tx_id, cid, budget)
            return _unavailable(tx_id, spec.name, TIMEOUT,
                                f"exceeded {budget:.3f}s budget", cid, ms)
        except Exception as exc:
            ms = (time.perf_counter() - t0) * 1000
            logger.error("engine=%s tx=%s cid=%s failed: %s",
                         spec.name, tx_id, cid, exc)
            return _unavailable(tx_id, spec.name, FAILED, str(exc), cid, ms)

        return _normalize(raw, tx_id, spec.name, cid, (time.perf_counter() - t0) * 1000)

    @staticmethod
    def summary(results, specs):
        required = {s.name for s in specs if s.required}
        # not_applicable is LEGITIMATE (e.g. no device_id) -> NOT a failure.
        broken = [r["engine"] for r in results
                  if r["status"] in (FAILED, TIMEOUT) and r["engine"] in required]
        na = [r["engine"] for r in results if r["status"] == NOT_APPLICABLE]
        return {"engines": {r["engine"]: r["status"] for r in results},
                "unavailable_required": broken, "not_applicable": na,
                "degraded": bool(broken)}