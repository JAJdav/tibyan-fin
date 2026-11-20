import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.schemas import TransactionIn

BASE_TS = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)  # noon UTC, safely in the past


def make_tx(**overrides) -> TransactionIn:
    data = {
        "transaction_id": "TX1",
        "customer_id": "C1",
        "account_id": "A1",
        "merchant_id": "M1",
        "amount": 100.0,
        "currency": "SAR",
        "timestamp": BASE_TS.isoformat(),
        "device_id": "D1",
        "country": "SA",
    }
    data.update(overrides)
    return TransactionIn(**data)


@pytest.fixture
def tx_factory():
    return make_tx


@pytest.fixture
def base_ts():
    return BASE_TS


@pytest.fixture
def minutes():
    return lambda m: timedelta(minutes=m)
