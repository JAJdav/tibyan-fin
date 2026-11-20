import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.persistence.db import get_engine


@pytest.fixture(scope="module")
def client():
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip("MySQL unavailable: " + str(exc))
    sql = Path("scripts/init_db.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        for statement in sql.split(";"):
            if statement.strip():
                conn.execute(text(statement))
    with TestClient(app) as c:
        yield c


def body(tid):
    return {"transaction_id": tid, "amount": "250.75", "currency": "USD",
            "event_time": datetime.now(timezone.utc).isoformat(),
            "customer_id": "C-M2", "account_id": "A-M2", "channel": "transfer"}


def test_duplicate_is_idempotent(client):
    tid = "M2-" + uuid.uuid4().hex[:12]
    payload = body(tid)
    first = client.post("/api/v1/transactions", json=payload)
    assert first.status_code == 200, first.text
    a = first.json()
    assert a["decision"] == "FLAG" and a["degraded"] is True
    assert a["combined_risk_score"] is None
    second = client.post("/api/v1/transactions", json=payload)
    assert second.status_code == 200
    b = second.json()
    assert b["decision_id"] == a["decision_id"] and b["idempotent_replay"] is True
    with get_engine().begin() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM risk_decisions WHERE transaction_id=:t"),
                         {"t": tid}).scalar()
        o = conn.execute(text("SELECT COUNT(*) FROM outbox_events WHERE transaction_id=:t"),
                         {"t": tid}).scalar()
    assert n == 1 and o == 1
    assert client.get("/api/v1/transactions/" + tid).json()["decision_id"] == a["decision_id"]
    inv = client.get("/api/v1/investigations/" + tid)
    assert inv.status_code == 202 and inv.json()["status"] == "pending"


def test_changed_payload_conflicts(client):
    tid = "M2-C-" + uuid.uuid4().hex[:12]
    payload = body(tid)
    assert client.post("/api/v1/transactions", json=payload).status_code == 200
    changed = dict(payload); changed["amount"] = "251.75"
    assert client.post("/api/v1/transactions", json=changed).status_code == 409
