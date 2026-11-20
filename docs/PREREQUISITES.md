# Prerequisites

## Required now (this stage)

| Tool | Version | Why | Check |
|---|---|---|---|
| Python | 3.11+ (3.12/3.13 fine) | API and tests. `bisect.insort(key=...)` needs 3.10+ | `python --version` |
| pip | recent | Install dependencies | `pip --version` |
| Docker Desktop | recent | Runs n8n (and the API container) | `docker --version` and `docker compose version` |
| Git | any | Version control | `git --version` |
| A terminal | PowerShell is fine | | |

Docker Desktop on Windows needs WSL 2 enabled. If Docker is a problem, you can run n8n without it:
install Node.js 20+ and run `npx n8n`, then use `http://localhost:8000` as the API URL (see below).

## Ports used

| Port | Service |
|---|---|
| 8000 | FastAPI |
| 5678 | n8n |

If a port is busy, change the left side of the mapping in `docker-compose.yml` and in the commands you run.

## Networking rule that trips most people

| n8n runs… | Use this API URL inside n8n |
|---|---|
| in Docker compose (default here) | `http://api:8000` |
| in Docker, API on your PC (uvicorn) | `http://host.docker.internal:8000` |
| outside Docker (`npx n8n`) | `http://localhost:8000` |

Inside a container, `localhost` means the container itself, not your PC. The workflow reads `FRAUD_API_URL`
(set in `docker-compose.yml`) and falls back to `http://api:8000`.

## Not needed yet (later stages)

MySQL, Redis, DuckDB/Parquet, scikit-learn/XGBoost, NetworkX, an LLM API key, Power BI, Prometheus/Grafana, Kafka.
Do not install them now.

## What only you can provide

1. **The dataset** (CSV/Parquet/SQL dump) in `data/raw/`, plus any label column and a short description of each field.
2. **Your reporting threshold** if it is not 10,000 (rule R003) and your **high-risk country list** (rule R007).
3. **Your timezone** if not `Asia/Riyadh` (set `TZ` in `.env`). Night-hours rule R010 uses UTC regardless.
4. Later: an LLM provider choice and API key, and MySQL/Redis credentials.

## Verify the setup

```powershell
python --version
pip install -r requirements.txt -r requirements-analysis.txt
pytest -q                      # 67 passed
uvicorn app.main:app --port 8000
curl.exe http://localhost:8000/health
```
