from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from tests.conftest import make_tx


def test_valid_transaction_normalises_currency_and_timestamp():
    tx = make_tx(currency="sar", timestamp="2026-11-01T15:00:00+03:00")
    assert tx.currency == "SAR"
    assert tx.timestamp == datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def test_naive_timestamp_is_treated_as_utc():
    tx = make_tx(timestamp="2026-11-01T12:00:00")
    assert tx.timestamp.tzinfo == timezone.utc


@pytest.mark.parametrize("amount", [0, -5, "abc", float("inf"), float("nan")])
def test_invalid_amounts_rejected(amount):
    with pytest.raises(ValidationError):
        make_tx(amount=amount)


@pytest.mark.parametrize("field,value", [
    ("transaction_id", ""),
    ("transaction_id", "has space"),
    ("customer_id", "x" * 65),
    ("currency", "SARR"),
    ("country", "SAU"),
    ("ip_address", "999.1.1.1"),
    ("channel", "carrier_pigeon"),
])
def test_invalid_fields_rejected(field, value):
    with pytest.raises(ValidationError):
        make_tx(**{field: value})


def test_future_timestamp_rejected():
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    with pytest.raises(ValidationError):
        make_tx(timestamp=future.isoformat())


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        make_tx(unexpected="x")


def test_missing_required_field_rejected():
    with pytest.raises(ValidationError):
        from app.schemas import TransactionIn
        TransactionIn(transaction_id="T", customer_id="C")
