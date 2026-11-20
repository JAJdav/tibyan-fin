## ADR-007 — Local Qwen via Ollama for investigation reports
- **Problem:** explanations required; no budget/latency tolerance for a cloud dependency in a live demo.
- **Decision:** Ollama native on Windows, `qwen3:8b` default, `/api/chat` with a Pydantic JSON schema in `format`, temperature 0, async worker only [[1]].
- **Alternatives:** cloud API (cost/network risk); LM Studio/vLLM (fine, but vLLM's default port 8000 collides with FastAPI); templates only (weaker narratives).
- **Trade-offs:** local latency + VRAM; single-model concurrency; quality below large hosted models.
- **Failure:** server down ⇒ job pending + backoff; invalid JSON ⇒ ≤2 repair retries ⇒ labelled template fallback.
- **Scaling:** swap `LLM_BASE_URL` to any OpenAI-compatible server; contract unchanged.

## ADR-008 — Synthetic dataset disclosure
- **Problem:** the data is synthetic; performance claims could mislead.
- **Decision:** record source, generator, license and SHA256 in `docs/DATASET_PROVENANCE.md`; label every metric "synthetic data"; exclude simulator-derived leakage columns.
- **Alternatives:** presenting results unqualified — rejected as fabrication-adjacent.
- **Trade-offs:** weaker headline claims, stronger credibility.
- **Failure:** unknown provenance ⇒ mark "unverified" and restrict claims to pipeline behaviour.
- **Note:** IBM's AML data is fully synthetic and released under CDLA-Sharing-1.0 [[21]] — confirm the actual source before citing it.