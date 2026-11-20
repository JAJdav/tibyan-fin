# Local LLM (Qwen via Ollama) — Investigation Service

## 1. Why local
No API cost, no network dependency during the demo, no data egress. Cost: latency + VRAM are now our problem.
The LLM stays **strictly asynchronous** — it never touches the authorization path.

## 2. Runtime
Install Ollama **natively on Windows** (not Docker — GPU passthrough on Docker Desktop/WSL2 adds risk we don't need in 7 days).

```powershell
ollama serve                 # listens on 127.0.0.1:11434
ollama pull qwen3:8b
ollama list
```

## 3. Model selection (verified pull tags, Nov 2026)

| Hardware | Tag | Download | Context |
|---|---|---|---|
| CPU only / 8 GB RAM | `qwen3:4b` | 2.5 GB | 256K [[9]] |
| GPU 8 GB VRAM | `qwen3:8b` | 5.2 GB | 40K [[9]] |
| GPU 12–16 GB | `qwen3:14b` | 9.3 GB | 40K [[9]] |
| GPU 24 GB | `qwen3.6:27b-q4_K_M` | 17 GB | 256K [[13]] |

**Default for this hackathon: `qwen3:8b`.** Investigation reports are short, evidence-bound JSON — a 27B model
buys little and costs latency. Record the exact tag in every report (`llm_model`).

## 4. Structured output (the critical capability)
Ollama accepts a **JSON schema in the `format` field** of `/api/chat`, constraining generation to that schema [[1]].
Pass the Pydantic schema and validate the response with the same model [[1]].

```python
resp = httpx.post(f"{BASE}/api/chat", json={
    "model": MODEL,
    "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": evidence_json}],
    "stream": False,
    "format": Investigation.model_json_schema(),
    "options": {"temperature": 0, "num_ctx": 8192},
    "keep_alive": "30m",
}, timeout=120)
report = Investigation.model_validate_json(resp.json()["message"]["content"])
```

- `temperature: 0` for determinism [[1]].
- Also pass the schema as text inside the prompt to ground the model [[1]].
- OpenAI-compatible path `/v1/chat/completions` + `response_format` also works [[1]] — use it only if we later swap providers.
- **Do not use Ollama cloud**: it does not support structured outputs [[1]].
- If we ever enable streaming: Ollama ≥0.32.6 changed the OpenAI streaming wire shape [[12]] — we use `stream:false`, so unaffected.
- Thinking mode: disable for latency/determinism on thinking-capable Qwen tags; verify the flag against your installed Ollama version before relying on it.

## 5. Server tuning
```powershell
$env:OLLAMA_NUM_PARALLEL = "1"      # one report at a time; queue the rest
$env:OLLAMA_MAX_LOADED_MODELS = "1" # avoid VRAM thrash
$env:OLLAMA_KEEP_ALIVE = "30m"      # avoid cold-start on every job
```
Concurrency 1–2 is fine: reports are async. Measure queue depth, not request latency.

## 6. Ports (conflict avoided)
| Service | Port |
|---|---|
| FastAPI | 8000 |
| Ollama | 11434 |
| MySQL | 3306 |
| Redis | 6379 |
| LM Studio (if used instead) | 1234 |
| vLLM (if used instead) | **8001** — its default 8000 collides with FastAPI |

## 7. Prompt contract (`PROMPT_VERSION=inv-v1`)
System rules, verbatim:
1. Use **only** facts present in the supplied evidence bundle. Never invent entities, amounts, dates or relationships.
2. Every `evidence[].reference` MUST be an id supplied in the bundle. Unreferenced claims are forbidden.
3. ML scores are **predictions, not proof**. State this in `limitations`.
4. If evidence is missing or an engine returned `failed/timeout/not_applicable`, say so in `limitations`.
5. Separate observed facts (`evidence`) from interpretation (`investigation_summary`).
6. `sar_draft` is `null` unless AML indicators are present; it is a **draft for human review**, never a filing.
7. Output JSON matching the schema exactly. No prose outside JSON.

## 8. Validation & failure ladder
1. Pydantic schema validation.
2. **Reference resolution**: every `evidence[].reference` must exist in the stored detection artifacts → reject hallucinated references.
3. On failure: ≤2 retries with a repair prompt containing the validation errors.
4. Still failing → mark job `failed_validation`, emit a **deterministic template report** labelled `generated_by: template`.
5. Ollama unreachable → job stays `pending` with backoff; authorization unaffected; retry on worker restart.
6. `LLM_MODE=mock` → schema-valid fixture labelled `llm_mode: mock`. Never presented as model output.

## 9. Acceptance test
`python scripts/llm_smoke_test.py` must print `VALID` plus measured latency, and reject a deliberately
hallucinated reference. Run it on Day 1 — this is the single biggest unknown in the stack.