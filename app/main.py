"""FastAPI gateway. Run: uvicorn app.main:app --reload --port 8000"""
from __future__ import annotations
import logging, uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from . import config
from .features import FeatureStore
from .idempotency import IdempotencyStore
from .metrics import Metrics
from .ml.inference import MLInferenceEngine
from .graph.engine import RealtimeGraphEngine
from .orchestration.adapters import RulesAdapter, UnavailableRules
from .orchestration.detector import DetectionOrchestrator, EngineSpec
from .schemas import TransactionIn
from .service import IntakeService

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)
STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    metrics = Metrics()
    rules_engine = None
    try:
        from .rules import RulesEngine
        rules_engine = RulesEngine(config.load_rules_config())
        rules_fn = RulesAdapter(rules_engine)
        rules_state = "active"
    except FileNotFoundError:
        rules_state = "unavailable: config/rules.json missing"
        logger.error("config/rules.json missing -> RULES DISABLED; "
                     "every decision will be FLAG (degraded mode)")
        rules_fn = UnavailableRules("config/rules.json is missing")

    ml = MLInferenceEngine()
    gr = RealtimeGraphEngine()
    specs = [EngineSpec("rules", rules_fn, 0.150),
             EngineSpec("ml", ml.predict, 0.250),
             EngineSpec("graph", gr.evaluate, 0.150)]
    orch = DetectionOrchestrator(specs, overall_deadline_s=0.40, max_concurrency=64)

    STATE.update(metrics=metrics, rules_engine=rules_engine, rules_state=rules_state,
                 ml=ml, graph=gr, specs=specs,
                 service=IntakeService(rules_engine, FeatureStore(), IdempotencyStore(),
                                       metrics, orch, specs, graph=gr))
    logger.info("engines_ready rules=%s ml=%s graph=active", rules_state, ml.fraud_version)
    yield
    STATE.clear()


app = FastAPI(title="Fraud & AML Platform - M2 detection", version="0.2.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    STATE["metrics"].inc("rejected")
    errors = [{"field": ".".join(str(p) for p in e["loc"] if p != "body"),
               "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"status": "rejected", "errors": errors})


@app.post("/api/v1/transactions")
async def submit_transaction(tx: TransactionIn,
                             x_correlation_id: str | None = Header(default=None)):
    cid = x_correlation_id or str(uuid.uuid4())
    status, body = await STATE["service"].process(tx, cid)
    return JSONResponse(status_code=status, content=body, headers={"X-Correlation-ID": cid})


@app.get("/api/v1/transactions/{transaction_id}")
async def get_transaction(transaction_id: str):
    stored = STATE["service"].idem.get(transaction_id)
    if stored is None:
        return JSONResponse(status_code=404,
                            content={"status": "not_found", "transaction_id": transaction_id})
    return stored


@app.get("/api/v1/rules")
async def list_rules():
    if STATE["rules_engine"] is None:
        return JSONResponse(status_code=503,
                            content={"status": "unavailable", "reason": STATE["rules_state"]})
    return config.load_rules_config()


@app.get("/api/v1/metrics")
async def get_metrics():
    return STATE["metrics"].snapshot()


@app.get("/health")
async def health():
    svc = STATE["service"]
    return {
        "status": "ok", "stage": "2-detection",
        "rules_version": getattr(STATE["rules_engine"], "version", None),
        "feature_version": config.FEATURE_VERSION,
        "engines": {"rules": STATE["rules_state"], "ml": STATE["ml"].fraud_version,
                    "graph": "active"},
        "graph_nodes": STATE["graph"].graph.number_of_nodes(),
        "stores": "in-memory (MySQL/Redis not wired)",
        "customers_tracked": svc.features.customer_count(),
        "transactions_stored": len(svc.idem),
    }