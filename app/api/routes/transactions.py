import time

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.schemas import TransactionDecisionResponse, TransactionSubmission, canonical_hash
from app.core.logging import log_event
from app.decision.scaffold import build_scaffold_decision
from app.persistence.db import get_engine
from app.persistence import repositories as repo

router = APIRouter()


@router.post("/transactions", response_model=TransactionDecisionResponse)
def submit_transaction(payload: TransactionSubmission, request: Request,
                       idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    start = time.perf_counter()
    cid = getattr(request.state, "correlation_id", None)
    key = idempotency_key or payload.transaction_id
    h = canonical_hash(payload)
    engine = get_engine()
    try:
        with engine.begin() as conn:
            existing = repo.find_idempotency(conn, key, payload.transaction_id)
            if existing:
                if existing["transaction_id"] != payload.transaction_id or existing["request_hash"] != h:
                    raise HTTPException(409, "Idempotency key or transaction id reused with different payload")
                resp = existing["response_json"]
                resp["idempotent_replay"] = True
                resp["correlation_id"] = cid
                log_event("transaction.idempotent_replay", transaction_id=payload.transaction_id,
                          correlation_id=cid)
                return resp

            tx = repo.get_transaction(conn, payload.transaction_id)
            if tx:
                if tx["request_hash"] != h:
                    raise HTTPException(409, "Transaction id reused with different payload")
                resp = repo.build_response(conn, payload.transaction_id, cid, replay=True)
                if resp is None:
                    raise HTTPException(503, "Decision persistence incomplete")
                repo.insert_idempotency(conn, key, payload.transaction_id, h, resp)
                return resp

            repo.upsert_entity(conn, "customers", "customer_id", payload.customer_id)
            repo.upsert_entity(conn, "merchants", "merchant_id", payload.merchant_id)
            repo.insert_transaction(conn, payload, h)

            decision = build_scaffold_decision(payload.transaction_id, cid)
            for result in decision["engine_results"]:
                repo.insert_detection_result(conn, result)
            repo.insert_decision(conn, decision)
            repo.insert_investigation_pending(conn, payload.transaction_id)
            repo.insert_outbox(conn, payload.transaction_id, decision["decision_id"])

            ms = int((time.perf_counter() - start) * 1000)
            repo.set_processing_ms(conn, payload.transaction_id, ms)
            decision["processing_ms"] = ms
            repo.insert_idempotency(conn, key, payload.transaction_id, h, decision)
            log_event("transaction.persisted", transaction_id=payload.transaction_id,
                      decision_id=decision["decision_id"], correlation_id=cid, processing_ms=ms)
            return decision
    except HTTPException:
        raise
    except IntegrityError:
        try:
            with engine.connect() as conn:
                existing = repo.find_idempotency(conn, key, payload.transaction_id)
                if existing and existing["request_hash"] == h:
                    resp = existing["response_json"]
                    resp["idempotent_replay"] = True
                    resp["correlation_id"] = cid
                    return resp
        except Exception:
            pass
        raise HTTPException(409, "Conflicting transaction persistence")
    except Exception as exc:
        log_event("transaction.persistence_failed", transaction_id=payload.transaction_id,
                  correlation_id=cid, error=str(exc))
        raise HTTPException(503, "Operational persistence unavailable")


@router.get("/transactions/{transaction_id}", response_model=TransactionDecisionResponse)
def get_transaction_decision(transaction_id: str, request: Request):
    cid = getattr(request.state, "correlation_id", None)
    try:
        with get_engine().connect() as conn:
            resp = repo.build_response(conn, transaction_id, cid)
            if resp is None:
                raise HTTPException(404, "Transaction not found")
            return resp
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Operational persistence unavailable")


@router.get("/investigations/{transaction_id}")
def get_investigation_report(transaction_id: str):
    try:
        with get_engine().connect() as conn:
            inv = repo.get_investigation(conn, transaction_id)
            if inv is None:
                raise HTTPException(404, "Investigation not found")
            if inv.get("report_json") is not None:
                return inv["report_json"]
            return JSONResponse(status_code=202, content={
                "transaction_id": transaction_id, "status": inv["status"],
                "retry_count": inv.get("retry_count", 0)})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Operational persistence unavailable")
