#!/usr/bin/env python3
"""M0 - Prerequisite verification. Non-zero exit if a REQUIRED check fails."""
from __future__ import annotations
import importlib, os, socket, subprocess, sys
from pathlib import Path

REQUIRED = ["pandas", "numpy", "pyarrow", "fastapi", "pydantic", "sqlalchemy", "pymysql", "redis", "duckdb", "yaml"]
OPTIONAL = ["sklearn", "xgboost", "networkx", "httpx", "pytest", "locust", "prometheus_client"]
results, failed = [], False


def check(name, fn, required=True):
    global failed
    try:
        ok, detail = fn()
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    results.append((name, "PASS" if ok else ("FAIL" if required else "WARN"), detail))
    if not ok and required:
        failed = True


check("python>=3.10", lambda: (sys.version_info >= (3, 10), sys.version.split()[0]))
for m in REQUIRED:
    check(f"import {m}", lambda m=m: (True, getattr(importlib.import_module(m), "__version__", "ok")))
for m in OPTIONAL:
    check(f"import {m}", lambda m=m: (True, getattr(importlib.import_module(m), "__version__", "ok")), required=False)


def port(host, p):
    with socket.create_connection((host, p), timeout=2):
        return True, f"{host}:{p} reachable"


check("MySQL reachable", lambda: port(os.getenv("MYSQL_HOST", "127.0.0.1"), int(os.getenv("MYSQL_PORT", "3306"))), required=False)
check("Redis reachable", lambda: port(os.getenv("REDIS_HOST", "127.0.0.1"), int(os.getenv("REDIS_PORT", "6379"))), required=False)
check("docker", lambda: (True, subprocess.run(["docker", "--version"], capture_output=True, text=True, timeout=10).stdout.strip()), required=False)
check(".env present", lambda: (Path(".env").exists(), "copy .env.example -> .env"), required=False)
check("LLM key configured", lambda: (bool(os.getenv("LLM_API_KEY")), "set LLM_API_KEY or use LLM_MODE=mock"), required=False)

w = max(len(r[0]) for r in results)
for n, s, d in results:
    print(f"{n.ljust(w)}  {s:4}  {d}")
sys.exit(1 if failed else 0)