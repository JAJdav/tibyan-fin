from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.api.schemas import EngineResult, TransactionSubmission, canonical_hash


def payload():
    return {"transaction_id": "UNIT-001", "amount": "100.50", "currency": "usd",
            "event_time": datetime.now(timezone.utc).isoformat(), "customer_id": "C1"}


def test_normalization_and_hash_stability():
    a, b = TransactionSubmission(**payload()), TransactionSubmission(**payload())
    assert a.currency == "USD"
    assert a.amount == Decimal("100.50")
    assert canonical_hash(a) == canonical_hash(b)


def test_zero_amount_rejected():
    d = payload(); d["amount"] = "0"
    with pytest.raises(ValidationError):
        TransactionSubmission(**d)


def test_bad_currency_rejected():
    d = payload(); d["currency"] = "US1"
    with pytest.raises(ValidationError):
        TransactionSubmission(**d)


def test_completed_engine_requires_score():
    with pytest.raises(ValidationError):
        EngineResult(transaction_id="T", engine="rules", status="completed", risk_score=None)


def test_not_applicable_forbids_score():
    with pytest.raises(ValidationError):
        EngineResult(transaction_id="T", engine="ml", status="not_applicable", risk_score=0.0)


def test_health_and_docs_exist():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/health").status_code in (200, 503)
