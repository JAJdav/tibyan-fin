"""Feature engineering: one transaction + prior state -> one immutable snapshot (features-v2).

Leakage rules (enforced by tests):
  * a snapshot only uses events with timestamp <= the current transaction's timestamp;
  * the current transaction is added to state only AFTER its snapshot is built;
  * a feature that cannot be computed honestly is None, never 0/False.

State kept (in memory; Redis replaces it later behind the same two calls, snapshot() and record()):
  * per customer : recent transactions (30 days)
  * per device   : who used it (48 h)      -> shared-device features, later also graph edges
  * per merchant : recent activity (48 h)  -> merchant load features

FEATURE_SPECS is the single source of truth for what each feature means. The data dictionary,
the rule-config validator and the tests all read it.
"""
import bisect
import statistics
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import config
from .schemas import TransactionIn

# name, dtype, scope, nullable, description
FEATURE_SPECS: list[dict] = [
    # --- pass-through of the transaction itself (so rules only ever read the snapshot)
    dict(name="amount", dtype="float", scope="transaction", nullable=False, desc="Transaction amount."),
    dict(name="country_code", dtype="str", scope="transaction", nullable=True,
         desc="Country sent with the transaction (ISO 3166 alpha-2). None if not sent."),
    dict(name="channel", dtype="str", scope="transaction", nullable=True,
         desc="Channel sent with the transaction. None if not sent."),
    dict(name="merchant_category", dtype="str", scope="transaction", nullable=True,
         desc="Merchant category sent with the transaction. None if not sent."),
    # --- state / meta
    dict(name="history_count", dtype="int", scope="customer", nullable=False,
         desc="Prior transactions of this customer in the last 30 days."),
    dict(name="is_cold_start", dtype="bool", scope="customer", nullable=False,
         desc="True when history_count < MIN_HISTORY_FOR_STATS; statistics are not trusted."),
    # --- velocity (customer)
    dict(name="tx_count_5m", dtype="int", scope="customer", nullable=False,
         desc="Customer transactions in the trailing 5 minutes, including the current one."),
    dict(name="tx_count_1h", dtype="int", scope="customer", nullable=False,
         desc="Same, trailing 1 hour."),
    dict(name="tx_count_24h", dtype="int", scope="customer", nullable=False,
         desc="Same, trailing 24 hours."),
    dict(name="sum_amount_1h", dtype="float", scope="customer", nullable=False,
         desc="Customer spend in the trailing 1 hour including the current transaction."),
    dict(name="sum_amount_24h", dtype="float", scope="customer", nullable=False,
         desc="Customer spend in the trailing 24 hours including the current transaction."),
    dict(name="secs_since_last_tx", dtype="float", scope="customer", nullable=True,
         desc="Seconds since the customer's previous transaction. None on the first one."),
    # --- behaviour vs own history
    dict(name="avg_amount_30d", dtype="float", scope="customer", nullable=True,
         desc="Customer's mean prior amount (30 d). None with no history."),
    dict(name="std_amount_30d", dtype="float", scope="customer", nullable=True,
         desc="Population std of prior amounts. None with fewer than 2 prior transactions."),
    dict(name="amount_zscore", dtype="float", scope="customer", nullable=True,
         desc="(amount - mean) / std. None on cold start or zero variance."),
    dict(name="amount_to_avg_ratio", dtype="float", scope="customer", nullable=True,
         desc="amount / mean prior amount. None on cold start."),
    # --- novelty
    dict(name="is_new_merchant", dtype="bool", scope="customer", nullable=False,
         desc="Merchant not seen in this customer's 30-day history (True on the very first tx)."),
    dict(name="is_new_device", dtype="bool", scope="customer", nullable=True,
         desc="Device not seen in this customer's history. None if no device_id sent."),
    dict(name="is_new_country", dtype="bool", scope="customer", nullable=True,
         desc="Country not seen in this customer's history. None if no country sent."),
    dict(name="distinct_devices_24h", dtype="int", scope="customer", nullable=False,
         desc="Distinct devices the customer used in 24 h, including the current one."),
    dict(name="distinct_merchants_24h", dtype="int", scope="customer", nullable=False,
         desc="Distinct merchants the customer used in 24 h, including the current one."),
    # --- AML shape
    dict(name="amount_to_reporting_threshold", dtype="float", scope="customer", nullable=False,
         desc="amount / REPORTING_THRESHOLD."),
    dict(name="near_threshold_count_24h", dtype="int", scope="customer", nullable=False,
         desc="Customer transactions in 24 h whose amount sits just below the reporting threshold "
              "(structuring signal), including the current one if it does."),
    dict(name="is_round_amount", dtype="bool", scope="customer", nullable=False,
         desc="Amount >= 100 and a multiple of 100."),
    # --- cross-customer
    dict(name="device_distinct_customers_24h", dtype="int", scope="device", nullable=True,
         desc="Distinct customers seen on this device in 24 h, including the current customer. "
              "None if no device_id sent. >1 means a shared device."),
    dict(name="merchant_tx_count_1h", dtype="int", scope="merchant", nullable=False,
         desc="Transactions at this merchant in the trailing hour, including the current one."),
    # --- calendar (UTC)
    dict(name="hour_of_day_utc", dtype="int", scope="calendar", nullable=False, desc="0-23, UTC."),
    dict(name="day_of_week", dtype="int", scope="calendar", nullable=False, desc="Monday=0 .. Sunday=6, UTC."),
    dict(name="is_weekend", dtype="bool", scope="calendar", nullable=False, desc="Saturday or Sunday, UTC."),
]
FEATURE_NAMES = {s["name"] for s in FEATURE_SPECS}
META_KEYS = {"feature_version", "computed_at"}


@dataclass(frozen=True)
class Event:
    ts: datetime
    amount: float
    merchant_id: str
    device_id: Optional[str]
    country: Optional[str]


class FeatureStore:
    def __init__(self, history_days: int = None, max_events: int = None, min_history: int = None):
        self.history = timedelta(days=history_days or config.HISTORY_DAYS)
        self.shared_window = timedelta(hours=config.SHARED_INDEX_HOURS)
        self.max_events = max_events or config.MAX_EVENTS_PER_CUSTOMER
        self.min_history = min_history or config.MIN_HISTORY_FOR_STATS
        self.threshold = config.REPORTING_THRESHOLD
        self.near_low = self.threshold * (1 - config.NEAR_THRESHOLD_BAND)
        self._events: dict[str, list[Event]] = {}
        self._device: dict[str, list[tuple[datetime, str]]] = {}   # device_id -> [(ts, customer_id)]
        self._merchant: dict[str, list[datetime]] = {}              # merchant_id -> [ts]
        self._lock = threading.RLock()

    def _is_near(self, amount: float) -> bool:
        return self.near_low <= amount < self.threshold

    # ------------------------------------------------------------------ read
    def snapshot(self, tx: TransactionIn) -> dict:
        ts = tx.timestamp
        d24, h1, m5 = timedelta(hours=24), timedelta(hours=1), timedelta(minutes=5)
        with self._lock:
            prior = [e for e in self._events.get(tx.customer_id, []) if ts - self.history < e.ts <= ts]
            dev_hits = [(t, c) for t, c in self._device.get(tx.device_id, []) if ts - d24 < t <= ts] \
                if tx.device_id else None
            mer_hits = [t for t in self._merchant.get(tx.merchant_id, []) if ts - h1 < t <= ts]

        def within(w):
            return [e for e in prior if e.ts > ts - w]

        w5, w1h, w24 = within(m5), within(h1), within(d24)

        amounts = [e.amount for e in prior]
        n = len(amounts)
        mean = statistics.fmean(amounts) if n else None
        std = statistics.pstdev(amounts) if n >= 2 else None
        enough = n >= self.min_history
        zscore = (tx.amount - mean) / std if (enough and std) else None
        ratio = tx.amount / mean if (enough and mean) else None

        known_devices = {e.device_id for e in prior if e.device_id}
        devices_24h = {e.device_id for e in w24 if e.device_id} | ({tx.device_id} if tx.device_id else set())

        near_24h = sum(1 for e in w24 if self._is_near(e.amount)) + (1 if self._is_near(tx.amount) else 0)

        return {
            "feature_version": config.FEATURE_VERSION,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "amount": tx.amount,
            "country_code": tx.country,
            "channel": tx.channel,
            "merchant_category": tx.merchant_category,
            "history_count": n,
            "is_cold_start": not enough,
            "tx_count_5m": len(w5) + 1,
            "tx_count_1h": len(w1h) + 1,
            "tx_count_24h": len(w24) + 1,
            "sum_amount_1h": round(sum(e.amount for e in w1h) + tx.amount, 2),
            "sum_amount_24h": round(sum(e.amount for e in w24) + tx.amount, 2),
            "secs_since_last_tx": max(0.0, (ts - max(e.ts for e in prior)).total_seconds()) if prior else None,
            "avg_amount_30d": round(mean, 2) if mean is not None else None,
            "std_amount_30d": round(std, 2) if std is not None else None,
            "amount_zscore": round(zscore, 3) if zscore is not None else None,
            "amount_to_avg_ratio": round(ratio, 3) if ratio is not None else None,
            "is_new_merchant": tx.merchant_id not in {e.merchant_id for e in prior},
            "is_new_device": (tx.device_id not in known_devices) if tx.device_id else None,
            "is_new_country": (tx.country not in {e.country for e in prior if e.country}) if tx.country else None,
            "distinct_devices_24h": len(devices_24h),
            "distinct_merchants_24h": len({e.merchant_id for e in w24} | {tx.merchant_id}),
            "amount_to_reporting_threshold": round(tx.amount / self.threshold, 4),
            "near_threshold_count_24h": near_24h,
            "is_round_amount": tx.amount >= 100 and float(tx.amount).is_integer() and int(tx.amount) % 100 == 0,
            "device_distinct_customers_24h": (len({c for _, c in dev_hits} | {tx.customer_id})
                                              if dev_hits is not None else None),
            "merchant_tx_count_1h": len(mer_hits) + 1,
            "hour_of_day_utc": ts.hour,
            "day_of_week": ts.weekday(),
            "is_weekend": ts.weekday() >= 5,
        }

    # ----------------------------------------------------------------- write
    def record(self, tx: TransactionIn) -> None:
        """Add the transaction to state. Call only after the snapshot was built."""
        ev = Event(tx.timestamp, tx.amount, tx.merchant_id, tx.device_id, tx.country)
        with self._lock:
            lst = self._events.setdefault(tx.customer_id, [])
            bisect.insort(lst, ev, key=lambda e: e.ts)
            cutoff = lst[-1].ts - self.history
            while lst and lst[0].ts < cutoff:
                lst.pop(0)
            if len(lst) > self.max_events:
                del lst[: len(lst) - self.max_events]

            if tx.device_id:
                dl = self._device.setdefault(tx.device_id, [])
                bisect.insort(dl, (tx.timestamp, tx.customer_id), key=lambda x: x[0])
                self._prune_shared(dl, lambda x: x[0])
            ml = self._merchant.setdefault(tx.merchant_id, [])
            bisect.insort(ml, tx.timestamp)
            self._prune_shared(ml, lambda x: x)

    def _prune_shared(self, lst: list, ts_of) -> None:
        cutoff = ts_of(lst[-1]) - self.shared_window
        while lst and ts_of(lst[0]) < cutoff:
            lst.pop(0)

    def customer_count(self) -> int:
        with self._lock:
            return len(self._events)
