from datetime import timedelta

from app.features import FEATURE_NAMES, FEATURE_SPECS, META_KEYS, FeatureStore
from tests.conftest import BASE_TS, make_tx


def test_first_transaction_is_cold_start_with_no_history():
    store = FeatureStore()
    f = store.snapshot(make_tx())
    assert f["history_count"] == 0
    assert f["is_cold_start"] is True
    assert f["tx_count_5m"] == 1  # current transaction only
    assert f["secs_since_last_tx"] is None
    assert f["amount_zscore"] is None  # never fabricated without history


def test_snapshot_does_not_include_current_transaction_in_history():
    store = FeatureStore()
    tx = make_tx()
    store.snapshot(tx)
    assert store.snapshot(tx)["history_count"] == 0  # snapshot alone never records


def test_velocity_windows_count_prior_transactions():
    store = FeatureStore()
    for i in range(4):
        store.record(make_tx(transaction_id=f"P{i}", timestamp=(BASE_TS - timedelta(minutes=i)).isoformat()))
    store.record(make_tx(transaction_id="OLD", timestamp=(BASE_TS - timedelta(minutes=30)).isoformat()))
    f = store.snapshot(make_tx(transaction_id="NOW"))
    assert f["tx_count_5m"] == 5  # 4 prior + current
    assert f["tx_count_1h"] == 6
    assert f["secs_since_last_tx"] == 0.0


def test_future_events_are_ignored_for_out_of_order_arrival():
    store = FeatureStore()
    store.record(make_tx(transaction_id="LATER", timestamp=(BASE_TS + timedelta(minutes=2)).isoformat()))
    f = store.snapshot(make_tx(transaction_id="EARLIER"))
    assert f["history_count"] == 0  # a later event is not available at this tx's time


def test_amount_statistics_need_minimum_history():
    store = FeatureStore(min_history=5)
    for i in range(5):
        store.record(make_tx(transaction_id=f"H{i}", amount=100 + i * 10,
                             timestamp=(BASE_TS - timedelta(days=1, minutes=i)).isoformat()))
    f = store.snapshot(make_tx(transaction_id="BIG", amount=5000))
    assert f["is_cold_start"] is False
    assert f["amount_zscore"] is not None and f["amount_zscore"] > 3
    assert f["amount_to_avg_ratio"] > 10


def test_zero_variance_history_gives_no_zscore():
    store = FeatureStore(min_history=3)
    for i in range(3):
        store.record(make_tx(transaction_id=f"H{i}", amount=100,
                             timestamp=(BASE_TS - timedelta(hours=2, minutes=i)).isoformat()))
    f = store.snapshot(make_tx(transaction_id="X", amount=900))
    assert f["amount_zscore"] is None


def test_new_device_merchant_country_flags():
    store = FeatureStore()
    store.record(make_tx(transaction_id="H", timestamp=(BASE_TS - timedelta(hours=1)).isoformat()))
    f = store.snapshot(make_tx(transaction_id="N", device_id="D-NEW", merchant_id="M-NEW", country="AE"))
    assert f["is_new_device"] is True and f["is_new_merchant"] is True and f["is_new_country"] is True
    f2 = store.snapshot(make_tx(transaction_id="K"))
    assert f2["is_new_device"] is False and f2["is_new_merchant"] is False


def test_missing_device_yields_unknown_not_false():
    store = FeatureStore()
    f = store.snapshot(make_tx(device_id=None))
    assert f["is_new_device"] is None


def test_distinct_devices_24h_includes_current():
    store = FeatureStore()
    for i, d in enumerate(["D1", "D2"]):
        store.record(make_tx(transaction_id=f"H{i}", device_id=d,
                             timestamp=(BASE_TS - timedelta(hours=1, minutes=i)).isoformat()))
    assert store.snapshot(make_tx(transaction_id="N", device_id="D3"))["distinct_devices_24h"] == 3


def test_history_is_pruned_by_max_events():
    store = FeatureStore(max_events=3)
    for i in range(6):
        store.record(make_tx(transaction_id=f"H{i}", timestamp=(BASE_TS - timedelta(minutes=10 - i)).isoformat()))
    assert store.snapshot(make_tx(transaction_id="N", timestamp=(BASE_TS + timedelta(minutes=1)).isoformat()))[
        "history_count"] == 3


# ------------------------------------------------------------------ v2 additions
def test_snapshot_keys_match_the_feature_registry_exactly():
    snap = FeatureStore().snapshot(make_tx())
    assert set(snap) - META_KEYS == FEATURE_NAMES
    assert len(FEATURE_NAMES) == len(FEATURE_SPECS)  # no duplicate names


def test_nullable_flag_in_registry_is_honest():
    snap = FeatureStore().snapshot(make_tx(device_id=None, country=None, channel=None))
    for spec in FEATURE_SPECS:
        if snap[spec["name"]] is None:
            assert spec["nullable"], f"{spec['name']} returned None but is declared non-nullable"


def test_near_threshold_count_includes_current_and_prior():
    store = FeatureStore()
    store.record(make_tx(transaction_id="A", amount=9500, timestamp=(BASE_TS - timedelta(hours=2)).isoformat()))
    store.record(make_tx(transaction_id="B", amount=5000, timestamp=(BASE_TS - timedelta(hours=1)).isoformat()))
    assert store.snapshot(make_tx(transaction_id="C", amount=9900))["near_threshold_count_24h"] == 2
    assert store.snapshot(make_tx(transaction_id="D", amount=100))["near_threshold_count_24h"] == 1


def test_amount_at_threshold_is_not_near_threshold():
    assert FeatureStore().snapshot(make_tx(amount=10000))["near_threshold_count_24h"] == 0


def test_shared_device_counts_distinct_customers_including_current():
    store = FeatureStore()
    for i, c in enumerate(["C1", "C2", "C2"]):
        store.record(make_tx(transaction_id=f"S{i}", customer_id=c, device_id="DX",
                             timestamp=(BASE_TS - timedelta(hours=1, minutes=i)).isoformat()))
    assert store.snapshot(make_tx(transaction_id="N", customer_id="C3", device_id="DX"))["device_distinct_customers_24h"] == 3
    assert store.snapshot(make_tx(transaction_id="M", customer_id="C1", device_id="DX"))["device_distinct_customers_24h"] == 2


def test_shared_device_is_none_without_device_and_ignores_old_or_future_events():
    store = FeatureStore()
    store.record(make_tx(transaction_id="OLD", customer_id="C9", device_id="DX",
                         timestamp=(BASE_TS - timedelta(hours=30)).isoformat()))
    store.record(make_tx(transaction_id="FUT", customer_id="C8", device_id="DX",
                         timestamp=(BASE_TS + timedelta(minutes=5)).isoformat()))
    assert store.snapshot(make_tx(device_id=None))["device_distinct_customers_24h"] is None
    assert store.snapshot(make_tx(transaction_id="N", device_id="DX"))["device_distinct_customers_24h"] == 1


def test_merchant_load_counts_current_and_recent_only():
    store = FeatureStore()
    store.record(make_tx(transaction_id="A", customer_id="C2", timestamp=(BASE_TS - timedelta(minutes=10)).isoformat()))
    store.record(make_tx(transaction_id="B", customer_id="C3", timestamp=(BASE_TS - timedelta(hours=3)).isoformat()))
    assert store.snapshot(make_tx(transaction_id="N"))["merchant_tx_count_1h"] == 2


def test_passthrough_and_calendar_features():
    f = FeatureStore().snapshot(make_tx(amount=250, country="SA", channel="mobile", merchant_category="grocery"))
    assert (f["amount"], f["country_code"], f["channel"], f["merchant_category"]) == (250, "SA", "mobile", "grocery")
    assert f["is_weekend"] == (f["day_of_week"] >= 5)
