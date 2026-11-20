#!/usr/bin/env python3
"""
M0.2 - Local LLM structured-output smoke test.
The evidence bundle below is a TEST FIXTURE, not real detection output.

    python scripts/llm_smoke_test.py
    python scripts/llm_smoke_test.py --model qwen3:14b --openai
"""
from __future__ import annotations
import argparse, json, os, time
from typing import Literal
import httpx
from pydantic import BaseModel, ValidationError


class Evidence(BaseModel):
    source: Literal["rules", "ml", "graph", "transaction", "history"]
    reference: str
    observation: str


class Investigation(BaseModel):
    transaction_id: str
    investigation_summary: str
    evidence: list[Evidence]
    risk_indicators: list[str]
    limitations: list[str]
    recommended_investigation_steps: list[str]
    sar_draft: str | None = None


# --- TEST FIXTURE (synthetic, explicitly labelled) ---
BUNDLE = {
    "fixture": True,
    "transaction_id": "SMOKE-0001",
    "decision": "FLAG",
    "combined_risk_score": 0.68,
    "available_evidence": [
        {"source": "rules", "reference": "R-001", "fact": "7 transactions in 5 minutes; configured threshold is 3."},
        {"source": "ml", "reference": "fraud-v1", "fact": "Model fraud probability 0.71 (predictive, not proof)."},
        {"source": "graph", "reference": "G-002", "fact": "Device D-9 linked to 4 distinct accounts in 24h."},
    ],
    "missing_evidence": ["Merchant history unavailable (not_applicable)."],
}
SYSTEM = (
    "You are an AML investigation assistant. Use ONLY facts in the supplied bundle. "
    "Every evidence[].reference MUST be one of the ids in available_evidence. Never invent facts. "
    "ML scores are predictions, not proof - say so in limitations. "
    "Mention missing evidence in limitations. sar_draft is null unless AML indicators exist. "
    "Return JSON matching this schema exactly:\n" + json.dumps(Investigation.model_json_schema())
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434"))
    ap.add_argument("--model", default=os.getenv("LLM_MODEL", "qwen3:8b"))
    ap.add_argument("--openai", action="store_true", help="use /v1/chat/completions instead of /api/chat")
    a = ap.parse_args()

    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(BUNDLE)}]
    schema = Investigation.model_json_schema()

    if a.openai:
        url = f"{a.base}/v1/chat/completions"
        payload = {"model": a.model, "messages": msgs, "stream": False, "temperature": 0,
                   "response_format": {"type": "json_schema",
                                       "json_schema": {"name": "investigation", "schema": schema, "strict": True}}}
        extract = lambda r: r.json()["choices"][0]["message"]["content"]
    else:
        url = f"{a.base}/api/chat"
        payload = {"model": a.model, "messages": msgs, "stream": False, "format": schema,
                   "options": {"temperature": 0, "num_ctx": 8192}, "keep_alive": "30m"}
        extract = lambda r: r.json()["message"]["content"]

    t0 = time.perf_counter()
    try:
        r = httpx.post(url, json=payload, timeout=float(os.getenv("LLM_TIMEOUT_S", "120")))
        r.raise_for_status()
    except Exception as exc:
        print(f"[FAIL] transport: {type(exc).__name__}: {exc}")
        print("       Is `ollama serve` running and is the model pulled? `ollama list`")
        raise SystemExit(1)
    ms = (time.perf_counter() - t0) * 1000
    raw = extract(r)

    try:
        rep = Investigation.model_validate_json(raw)
    except ValidationError as exc:
        print(f"[FAIL] schema validation after {ms:.0f} ms:\n{exc}\nRAW:\n{raw[:1500]}")
        raise SystemExit(1)

    allowed = {e["reference"] for e in BUNDLE["available_evidence"]}
    bad = [e.reference for e in rep.evidence if e.reference not in allowed]
    print(f"[OK] schema VALID in {ms:.0f} ms | model={a.model} | evidence items={len(rep.evidence)}")
    if bad:
        print(f"[FAIL] hallucinated references (must trigger retry/repair in M6): {bad}")
        raise SystemExit(2)
    print("[OK] all evidence references resolve to supplied ids")
    print(json.dumps(rep.model_dump(), indent=2)[:1200])


if __name__ == "__main__":
    main()