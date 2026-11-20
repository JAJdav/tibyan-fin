from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client():
    # fresh in-memory state for every test
    from app.features import FeatureStore
    from app.idempotency import IdempotencyStore
    from app.metrics import Metrics
    from app.service import IntakeService

    main.metrics = Metrics()
    main.service = IntakeService(main.rules_engine, FeatureStore(), IdempotencyStore(), main.metrics)
    return TestClient(main.app)


def payload(**kw):
    p = {
        "transaction_id": "TX-1", "customer_id": "C1", "account_id": "A1", "merchant_id": "M1",
        "amount": 250.0, "currency": "SAR",
        "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0).isoformat(),
        "device_id": "D1", "country": "SA",
    }
    p.update(kw)
    return p


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["engines"]["rules"] == "active"


def test_happy_path_response_shape(client):
    r = client.post("/api/v1/transactions", json=payload())
    assert r.status_code == 200
    b = r.json()
    assert b["status"] == "processed" and b["idempotent_replay"] is False
    assert set(b["engines"]) == {"rules", "ml", "graph"}
    assert b["engines"]["ml"]["status"] == "not_applicable"
    assert b["engines"]["ml"]["risk_score"] is None  # not-run is never reported as zero risk
    assert b["decision"] is None
    assert r.headers["X-Correlation-ID"] == b["correlation_id"]


def test_correlation_id_is_echoed(client):
    r = client.post("/api/v1/transactions", json=payload(), headers={"X-Correlation-ID": "abc-123"})
    assert r.json()["correlation_id"] == "abc-123"


def test_duplicate_returns_same_result_without_reprocessing(client):
    first = client.post("/api/v1/transactions", json=payload()).json()
    second = client.post("/api/v1/transactions", json=payload()).json()
    assert second["idempotent_replay"] is True
    assert second["features"] == first["features"]
    assert main.service.features.snapshot(
        main.TransactionIn(**payload(transaction_id="probe")))["history_count"] == 1  # recorded once


def test_same_id_different_payload_is_conflict(client):
    client.post("/api/v1/transactions", json=payload())
    r = client.post("/api/v1/transactions", json=payload(amount=999))
    assert r.status_code == 409 and r.json()["status"] == "conflict"


def test_invalid_payload_returns_422_with_field_errors(client):
    r = client.post("/api/v1/transactions", json=payload(amount=-1, currency="XX"))
    assert r.status_code == 422
    body = r.json()
    assert body["status"] == "rejected"
    assert {e["field"] for e in body["errors"]} >= {"amount", "currency"}


def test_rejected_transaction_does_not_consume_the_id(client):
    client.post("/api/v1/transactions", json=payload(amount=-1))
    assert client.post("/api/v1/transactions", json=payload()).status_code == 200


def test_near_threshold_amount_is_flagged_but_not_actioned_via_api(client):
    b = client.post("/api/v1/transactions", json=payload(transaction_id="S1", amount=9500)).json()
    assert "NEAR_THRESHOLD_AMOUNT" in b["engines"]["rules"]["reason_codes"]
    assert b["engines"]["rules"]["rule_action"] == "none"  # a single near-threshold amount alone is not enough


def test_get_transaction_and_404(client):
    client.post("/api/v1/transactions", json=payload())
    assert client.get("/api/v1/transactions/TX-1").json()["transaction_id"] == "TX-1"
    assert client.get("/api/v1/transactions/NOPE").status_code == 404


def test_metrics_and_rules_endpoints(client):
    client.post("/api/v1/transactions", json=payload())
    m = client.get("/api/v1/metrics").json()
    assert m["counters"]["processed"] == 1
    assert client.get("/api/v1/rules").json()["version"] == "rules-v2"
