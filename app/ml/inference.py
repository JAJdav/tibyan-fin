"""ML fraud inference: trained model if present, else a transparent placeholder."""
from __future__ import annotations
import asyncio, logging, os, time
from typing import Any, Dict

logger = logging.getLogger(__name__)

MODEL_FEATURES = [
    "amount_to_reporting_threshold", "tx_count_5m", "tx_count_1h", "tx_count_24h",
    "amount_zscore", "amount_to_avg_ratio", "device_distinct_customers_24h",
    "near_threshold_count_24h", "distinct_devices_24h", "hour_of_day_utc",
]


class MLInferenceEngine:
    def __init__(self, model_path: str = "models/fraud_xgb_v1.joblib"):
        self.model = None
        self.fraud_version = "mock-v1"
        self.aml_version = None
        if os.path.exists(model_path):
            import joblib
            self.model = joblib.load(model_path)
            self.fraud_version = "xgb-v1"
            logger.info("loaded trained fraud model from %s", model_path)
        else:
            logger.warning("no trained model at %s -> placeholder scoring, NOT a model", model_path)

    def predict_sync(self, features: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.perf_counter()
        tx_id = features.get("transaction_id", "UNKNOWN")
        missing = [f for f in MODEL_FEATURES if features.get(f) is None]

        if self.model is not None:
            import numpy as np
            X = np.array([[float("nan") if features.get(f) is None else float(features[f])
                           for f in MODEL_FEATURES]], dtype=float)
            score = float(self.model.predict_proba(X)[0, 1])
        else:
            parts = []
            a = features.get("amount_to_reporting_threshold")
            if a is not None: parts.append((min(1.0, a), 0.30))
            v = features.get("tx_count_5m")
            if v is not None: parts.append((min(1.0, max(0, v - 1) / 9), 0.25))
            z = features.get("amount_zscore")
            if z is not None: parts.append((min(1.0, max(0.0, z) / 5), 0.25))
            s = features.get("near_threshold_count_24h")
            if s is not None: parts.append((min(1.0, max(0, s - 1) / 4), 0.20))
            wsum = sum(w for _, w in parts)
            score = sum(v * w for v, w in parts) / wsum if wsum else 0.0

        return {"transaction_id": tx_id, "engine": "ml", "status": "completed",
                "risk_score": round(score, 4),
                "reason_codes": ["ML_FRAUD_ELEVATED"] if score > 0.5 else [],
                "evidence": [f"fraud scorer {self.fraud_version} score={score:.4f}"],
                "model_version": self.fraud_version,
                "details": {"missing_features": missing, "trained": self.model is not None},
                "processing_ms": round((time.perf_counter() - t0) * 1000, 3)}

    async def predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        return await asyncio.to_thread(self.predict_sync, features)