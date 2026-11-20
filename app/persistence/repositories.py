import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.api.schemas import TransactionSubmission


def utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def jd(value) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)


def jl(value):
    if value is None or isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def rd(row) -> dict | None:
    return dict(row._mapping) if row is not None else None


def find_idempotency(conn: Connection, key: str, tid: str) -> dict | None:
    row = conn.execute(text("SELECT * FROM idempotency_records WHERE idempotency_key=:k "
                            "OR transaction_id=:t LIMIT 1"), {"k": key, "t": tid}).first()
    data = rd(row)
    if data:
        data["response_json"] = jl(data["response_json"])
    return data


def get_transaction(conn: Connection, tid: str) -> dict | None:
    return rd(conn.execute(text("SELECT * FROM transactions WHERE transaction_id=:t"),
                           {"t": tid}).first())


def upsert_entity(conn: Connection, table: str, col: str, value: str | None) -> None:
    if not value:
        return
    conn.execute(text("INSERT IGNORE INTO " + table + " (" + col + ", attributes) "
                      "VALUES (:v, :a)"), {"v": value, "a": jd({})})


def insert_transaction(conn: Connection, p: TransactionSubmission, request_hash: str) -> None:
    conn.execute(text(
        "INSERT INTO transactions (transaction_id, customer_id, merchant_id, account_id, "
        "device_id, counterparty_account_id, amount, currency, direction, channel, "
        "event_time, received_at, request_hash, raw_payload, metadata) VALUES "
        "(:transaction_id, :customer_id, :merchant_id, :account_id, :device_id, "
        ":counterparty_account_id, :amount, :currency, :direction, :channel, "
        ":event_time, :received_at, :request_hash, :raw_payload, :metadata)"),
        {"transaction_id": p.transaction_id, "customer_id": p.customer_id,
         "merchant_id": p.merchant_id, "account_id": p.account_id, "device_id": p.device_id,
         "counterparty_account_id": p.counterparty_account_id, "amount": float(p.amount),
         "currency": p.currency, "direction": p.direction, "channel": p.channel,
         "event_time": utc_naive(p.event_time), "received_at": now_naive(),
         "request_hash": request_hash, "raw_payload": jd(p.model_dump(mode="json")),
         "metadata": jd(p.metadata)})


def insert_detection_result(conn: Connection, r: dict) -> None:
    conn.execute(text(
        "INSERT INTO detection_results (transaction_id, engine, status, risk_score, "
        "reason_codes, evidence, processing_ms, engine_version, degraded) VALUES "
        "(:transaction_id, :engine, :status, :risk_score, :reason_codes, :evidence, "
        ":processing_ms, :engine_version, :degraded) ON DUPLICATE KEY UPDATE "
        "status=VALUES(status), risk_score=VALUES(risk_score), "
        "reason_codes=VALUES(reason_codes), evidence=VALUES(evidence), "
        "processing_ms=VALUES(processing_ms), engine_version=VALUES(engine_version), "
        "degraded=VALUES(degraded)"),
        {**r, "reason_codes": jd(r.get("reason_codes", [])), "evidence": jd(r.get("evidence", []))})


def insert_decision(conn: Connection, d: dict) -> None:
    conn.execute(text(
        "INSERT INTO risk_decisions (decision_id, transaction_id, decision, "
        "combined_risk_score, fraud_risk_score, aml_risk_score, reason_codes, policy_version, "
        "feature_version, model_versions, degraded, missing_features, processing_ms, "
        "decision_basis, correlation_id) VALUES (:decision_id, :transaction_id, :decision, "
        ":combined_risk_score, :fraud_risk_score, :aml_risk_score, :reason_codes, "
        ":policy_version, :feature_version, :model_versions, :degraded, :missing_features, "
        ":processing_ms, :decision_basis, :correlation_id)"),
        {**d, "reason_codes": jd(d.get("reason_codes", [])),
         "model_versions": jd(d.get("model_versions", {})),
         "missing_features": jd(d.get("missing_features", []))})


def set_processing_ms(conn: Connection, tid: str, ms: int) -> None:
    conn.execute(text("UPDATE risk_decisions SET processing_ms=:m WHERE transaction_id=:t"),
                 {"m": ms, "t": tid})


def insert_investigation_pending(conn: Connection, tid: str) -> None:
    conn.execute(text("INSERT IGNORE INTO investigations (transaction_id, status, retry_count) "
                      "VALUES (:t, 'pending', 0)"), {"t": tid})


def insert_outbox(conn: Connection, tid: str, decision_id: str) -> None:
    conn.execute(text(
        "INSERT INTO outbox_events (event_id, event_type, aggregate_type, aggregate_id, "
        "transaction_id, payload, status) VALUES (:e, 'investigation.requested', "
        "'transaction', :t, :t, :p, 'pending')"),
        {"e": str(uuid.uuid4()), "t": tid, "p": jd({"transaction_id": tid,
                                                   "decision_id": decision_id})})


def insert_idempotency(conn: Connection, key: str, tid: str, h: str, resp: dict) -> None:
    conn.execute(text(
        "INSERT IGNORE INTO idempotency_records (idempotency_key, transaction_id, "
        "request_hash, response_json, status) VALUES (:k, :t, :h, :r, 'completed')"),
        {"k": key, "t": tid, "h": h, "r": jd(resp)})


def get_investigation(conn: Connection, tid: str) -> dict | None:
    data = rd(conn.execute(text("SELECT * FROM investigations WHERE transaction_id=:t"),
                           {"t": tid}).first())
    if data and data.get("report_json") is not None:
        data["report_json"] = jl(data["report_json"])
    return data


def get_results(conn: Connection, tid: str) -> list[dict]:
    rows = conn.execute(text(
        "SELECT engine, status, risk_score, reason_codes, evidence, processing_ms, "
        "engine_version, degraded FROM detection_results WHERE transaction_id=:t "
        "ORDER BY engine"), {"t": tid}).all()
    out = []
    for row in rows:
        d = dict(row._mapping)
        d["transaction_id"] = tid
        d["reason_codes"] = jl(d["reason_codes"]) or []
        d["evidence"] = jl(d["evidence"]) or []
        d["risk_score"] = float(d["risk_score"]) if d["risk_score"] is not None else None
        out.append(d)
    return out


def build_response(conn: Connection, tid: str, cid: str | None = None,
                   replay: bool = False) -> dict | None:
    d = rd(conn.execute(text("SELECT * FROM risk_decisions WHERE transaction_id=:t"),
                        {"t": tid}).first())
    if not d:
        return None
    inv = get_investigation(conn, tid)
    f = lambda v: float(v) if v is not None else None
    return {"transaction_id": tid, "decision_id": d["decision_id"], "decision": d["decision"],
            "combined_risk_score": f(d["combined_risk_score"]),
            "fraud_risk_score": f(d["fraud_risk_score"]),
            "aml_risk_score": f(d["aml_risk_score"]),
            "engine_results": get_results(conn, tid),
            "reason_codes": jl(d["reason_codes"]) or [],
            "model_versions": jl(d["model_versions"]) or {},
            "policy_version": d["policy_version"], "feature_version": d["feature_version"],
            "degraded": bool(d["degraded"]),
            "missing_features": jl(d["missing_features"]) or [],
            "correlation_id": cid or d.get("correlation_id"),
            "processing_ms": d["processing_ms"], "idempotent_replay": replay,
            "decision_basis": d.get("decision_basis"),
            "investigation_status": inv["status"] if inv else None}
