# Prerequisites & Environment Setup

## 1. Host assumptions
- OS: Windows 10/11, PowerShell 5.1+ or 7.x. Project root: `C:\Users\Analy\Desktop\hackthon`
- Python **3.11** recommended (3.10 minimum). 3.13 may lack wheels for some ML deps — verify before upgrading.
- Git, and Docker Desktop with WSL2 backend (used for MySQL + Redis only).
- RAM: 16 GB recommended (pandas profiling + MySQL + Redis + API). 8 GB works with `--max-rows` reduced.

## 2. Service matrix

| Service | How it runs | Port | Required at | Notes |
|---|---|---|---|---|
| FastAPI/Uvicorn | local venv | 8000 | M1 | `uvicorn app.main:app --reload` |
| MySQL 8.0 | Docker | 3306 | M2 | authoritative operational store |
| Redis 7 | Docker | 6379 | M3 | no supported native Windows build; use Docker (or Memurai) |
| DuckDB | embedded library | — | M7 | **no server**; single-writer process only |
| Parquet | local filesystem | — | M7 | `data/analytical/` |
| LLM API | external HTTPS | — | M6 | provider-agnostic; `LLM_MODE=mock` for offline demo |
| Power BI Desktop | Windows app | — | M7 | not containerized |
| Prometheus/Grafana | Docker (commented) | 9090/3000 | Stage 2 | do not enable before MVP works |

## 3. Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env      # then edit secrets
docker compose up -d mysql redis
python scripts/check_env.py
```

Pin exact versions after first successful install: `pip freeze > requirements.lock.txt`.

## 4. MySQL
- Database `fraud_aml`, user `fraud_app` (least privilege: SELECT/INSERT/UPDATE/DELETE on that schema only).
- Charset `utf8mb4`, collation `utf8mb4_0900_ai_ci`, engine InnoDB.
- Driver `PyMySQL` + `cryptography` (required for MySQL 8 `caching_sha2_password`).
- Timezone: store **UTC** everywhere (`DATETIME(3)`), convert at presentation only.

## 5. Redis
- `maxmemory-policy noeviction` for feature state (evicting a velocity counter silently corrupts risk).
- Persistence AOF `everysec` in dev; feature state is rebuildable from MySQL, so loss = degraded mode, not data loss.

## 6. LLM configuration
| Variable | Purpose |
|---|---|
| `LLM_MODE` | `live` \| `mock` \| `disabled` |
| `LLM_PROVIDER` / `LLM_MODEL` | provider + model id recorded in every report |
| `LLM_BASE_URL` / `LLM_API_KEY` | endpoint + secret (never committed) |
| `LLM_TIMEOUT_S` / `LLM_MAX_RETRIES` | bounded call budget |

`mock` mode returns a **deterministic, schema-valid report clearly labelled `"llm_mode": "mock"`** — it must never be presented as real model output.

## 7. Power BI connectivity (decision required at M7)
Power BI has no first-class DuckDB connector. Options, in order of MVP simplicity:
1. **DuckDB → Parquet/CSV marts → Power BI** (folder/Parquet connector). Simplest, no drivers. Recommended for hackathon.
2. DuckDB → MySQL mart tables → Power BI MySQL connector (requires MySQL Connector/NET or ODBC driver installed).
3. DuckDB ODBC driver → Power BI ODBC. Most direct, but driver availability/version must be verified on the host.
Record the choice as an ADR. Do **not** claim a working dashboard before it is opened and refreshed.

## 8. Verification checklist
- [ ] `python scripts/check_env.py` exits 0
- [ ] `docker compose ps` shows mysql + redis healthy
- [ ] `docs/reports/*` generated from real data
- [ ] `.env` present and excluded from git
- [ ] LLM mode chosen and reachable (or mock explicitly selected)

## 9. Known constraints
- A single dev laptop will **not** sustain 1,000 TPS. Stage 1 reports measured numbers only; 1,000 TPS is a Stage 2 target requiring separate load generation and horizontal scaling.
- DuckDB is single-writer: analytics writes happen in a dedicated batch process, never in the API request path.