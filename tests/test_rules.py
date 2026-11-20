import copy
from datetime import timedelta

import pytest

from app.config import load_rules_config
from app.features import FeatureStore
from app.rules import ConfigError, RulesEngine, validate_config
from tests.conftest import BASE_TS, make_tx


@pytest.fixture
def cfg():
    return load_rules_config()


@pytest.fixture
def engine(cfg):
    return RulesEngine(cfg)


def run(engine, store, tx):
    return engine.evaluate(tx, store.snapshot(tx))


def rule(result, rid):
    return next(r for r in result["rules"] if r["rule_id"] == rid)


def typ(result, tid):
    return next(t for t in result["typologies"] if t["typology_id"] == tid)


def seed(store, n, *, amount=100, device="D1", customer="C1", start_minutes_ago=60 * 24 * 2, step_minutes=7):
    """n prior transactions, oldest first, all well before BASE_TS."""
    for i in range(n):
        store.record(make_tx(transaction_id=f"{customer}-H{i}", customer_id=customer, amount=amount + i,
                             device_id=device,
                             timestamp=(BASE_TS - timedelta(minutes=start_minutes_ago - i * step_minutes)).isoformat()))


# ------------------------------------------------------------------ config validation
def test_shipped_config_is_valid(cfg):
    validate_config(cfg)


def test_rule_with_unknown_feature_is_rejected(cfg):
    bad = copy.deepcopy(cfg)
    bad["rules"][0]["feature"] = "no_such_feature"
    with pytest.raises(ConfigError, match="unknown feature"):
        validate_config(bad)


def test_non_contiguous_bands_are_rejected(cfg):
    bad = copy.deepcopy(cfg)
    bad["rules"][0]["bands"][1]["lowerLimit"] = 5  # gap between .00 (upper 4) and .01
    with pytest.raises(ConfigError, match="contiguous"):
        validate_config(bad)


def test_typology_referencing_missing_subruleref_is_rejected(cfg):
    bad = copy.deepcopy(cfg)
    bad["typologies"][0]["rules"][0]["wghts"].append({"ref": ".99", "wght": 5})
    with pytest.raises(ConfigError, match=r"\.99"):
        validate_config(bad)


def test_typology_expression_must_match_rule_list(cfg):
    bad = copy.deepcopy(cfg)
    bad["typologies"][0]["expression"] = ["Add", "R001"]
    with pytest.raises(ConfigError, match="expression"):
        validate_config(bad)


def test_review_threshold_must_not_exceed_interdiction(cfg):
    bad = copy.deepcopy(cfg)
    bad["typologies"][0]["thresholds"] = {"review": 90, "interdiction": 50}
    with pytest.raises(ConfigError, match="review"):
        validate_config(bad)


# ------------------------------------------------------------------ band / case semantics
def test_band_boundaries_are_lower_inclusive_upper_exclusive(engine):
    # R011 bands: [null,1000) [1000,5000) [5000,10000) [10000,null)
    for amount, ref in [(999.99, ".00"), (1000, ".01"), (4999.99, ".01"), (5000, ".02"), (10000, ".03")]:
        r = run(engine, FeatureStore(), make_tx(amount=amount))
        assert rule(r, "R011")["subRuleRef"] == ref, amount


def test_case_matching_and_else(engine):
    s = FeatureStore()
    assert rule(run(engine, s, make_tx(country="XA")), "R007")["subRuleRef"] == ".01"
    assert rule(run(engine, s, make_tx(country="SA")), "R007")["subRuleRef"] == ".00"


def test_missing_feature_exits_instead_of_scoring_zero(engine):
    r = run(engine, FeatureStore(), make_tx(country=None))
    res = rule(r, "R007")
    assert res["status"] == "exit" and res["subRuleRef"] == ".x00" and res["flagged"] is False


# ------------------------------------------------------------------ cold start / exits
def test_history_rules_exit_on_cold_start(engine):
    r = run(engine, FeatureStore(), make_tx(amount=6000))
    assert rule(r, "R003")["status"] == "exit"
    assert rule(r, "R005")["status"] == "exit"
    assert rule(r, "R006")["status"] == "exit"  # no previous transaction
    assert r["coverage"] < 1


def test_typology_reports_incomplete_when_a_member_exited(engine):
    r = run(engine, FeatureStore(), make_tx())
    t = typ(r, "T002")
    assert t["complete"] is False
    assert {x["rule_id"] for x in t["not_evaluated"]} >= {"R003", "R005"}


# ------------------------------------------------------------------ individual rules through the engine
def test_velocity_bands_and_typology(engine):
    s = FeatureStore()
    for i in range(7):
        s.record(make_tx(transaction_id=f"B{i}", timestamp=(BASE_TS - timedelta(seconds=40 + i * 20)).isoformat()))
    r = run(engine, s, make_tx(transaction_id="NOW"))
    assert rule(r, "R001")["subRuleRef"] == ".02"  # 8 in 5 min -> [6,10)
    assert "UNUSUAL_VELOCITY" in r["reason_codes"]
    assert typ(r, "T001")["score"] >= 40 and r["rule_action"] in ("review", "interdiction")


def test_structuring_single_vs_repeated(engine):
    single = run(engine, FeatureStore(), make_tx(amount=9500))
    assert rule(single, "R004")["subRuleRef"] == ".01"
    assert typ(single, "T003")["action"] == "none"  # one near-threshold amount is not enough

    s = FeatureStore()
    s.record(make_tx(transaction_id="P1", amount=9400, timestamp=(BASE_TS - timedelta(hours=3)).isoformat()))
    repeated = run(engine, s, make_tx(transaction_id="P2", amount=9600))
    assert rule(repeated, "R004")["subRuleRef"] == ".02"
    assert "POSSIBLE_STRUCTURING" in repeated["reason_codes"]
    assert typ(repeated, "T003")["action"] == "review"


def test_amount_anomaly_and_new_device_drive_account_takeover(engine):
    s = FeatureStore()
    seed(s, 8, amount=100)
    r = run(engine, s, make_tx(transaction_id="ATO", amount=7000, device_id="D-STRANGER"))
    assert rule(r, "R003")["subRuleRef"] == ".03"
    assert rule(r, "R005")["subRuleRef"] == ".01"
    t = typ(r, "T002")
    assert t["score"] >= 50 and t["action"] in ("review", "interdiction")


def test_shared_device_across_customers(engine):
    s = FeatureStore()
    for i, c in enumerate(["C1", "C2"]):
        s.record(make_tx(transaction_id=f"X{i}", customer_id=c, device_id="D-SHARED",
                         timestamp=(BASE_TS - timedelta(hours=2, minutes=i)).isoformat()))
    r = run(engine, s, make_tx(transaction_id="X3", customer_id="C3", device_id="D-SHARED"))
    assert rule(r, "R012")["subRuleRef"] == ".02"
    assert "SHARED_DEVICE" in r["reason_codes"]
    assert typ(r, "T005")["score"] >= 60


def test_night_activity_uses_utc_hour(engine):
    night = BASE_TS.replace(hour=2).isoformat()
    assert rule(run(engine, FeatureStore(), make_tx(timestamp=night)), "R010")["flagged"] is True
    assert rule(run(engine, FeatureStore(), make_tx()), "R010")["flagged"] is False


def test_high_risk_country_typology(engine):
    r = run(engine, FeatureStore(), make_tx(country="XA", amount=12000, merchant_category="crypto"))
    t = typ(r, "T004")
    # R007 .01 (40) + R014 .01 (20) + R011 .03 (20) = 80: above review (50), below interdiction (90)
    assert {c["rule_id"]: c["wght"] for c in t["contributions"] if c["wght"]} == {"R007": 40, "R014": 20, "R011": 20}
    assert t["score"] == 80 and t["action"] == "review"


# ------------------------------------------------------------------ engine output contract
def test_clean_transaction_scores_zero_with_no_action(engine):
    r = run(engine, FeatureStore(), make_tx())
    assert r["risk_score"] == 0.0 and r["rule_action"] == "none" and r["triggered_count"] == 0
    assert r["status"] == "completed"


def test_result_contains_shared_engine_schema_and_tazama_fields(engine):
    r = run(engine, FeatureStore(), make_tx())
    for key in ("transaction_id", "engine", "status", "risk_score", "reason_codes", "evidence", "processing_ms"):
        assert key in r
    one = r["rules"][0]
    for key in ("id", "cfg", "subRuleRef", "reason", "status", "prcgTm", "feature", "value"):
        assert key in one
    assert one["id"] == "R001@1.0.0"


def test_typology_score_is_capped_at_100(cfg):
    cfg = copy.deepcopy(cfg)
    for m in cfg["typologies"][3]["rules"]:
        for w in m["wghts"]:
            w["wght"] = 100
    r = RulesEngine(cfg).evaluate(make_tx(country="XA", merchant_category="crypto", amount=20000),
                                  FeatureStore().snapshot(make_tx(country="XA", merchant_category="crypto", amount=20000)))
    assert typ(r, "T004")["score"] == 100 and r["risk_score"] == 1.0


def test_fraud_and_aml_scores_are_separate(engine):
    r = run(engine, FeatureStore(), make_tx(country="XA"))
    assert r["aml_rule_score"] > 0 and r["fraud_rule_score"] == 0


def test_crashing_rule_is_isolated_reported_and_not_counted_as_zero(engine, monkeypatch):
    import app.rules.engine as eng

    def boom(*a, **k):
        raise RuntimeError("bad rule")
    monkeypatch.setattr(eng, "_band", boom)
    r = run(engine, FeatureStore(), make_tx(country="XA"))
    assert r["errors"] and rule(r, "R001")["subRuleRef"] == ".err"
    assert rule(r, "R007")["flagged"] is True  # case-based rule still ran
    assert typ(r, "T001")["complete"] is False
