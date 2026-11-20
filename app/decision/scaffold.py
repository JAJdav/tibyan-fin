import uuid


# M2 PERSISTENCE SCAFFOLD ONLY - not the real decision engine.
# Engines are not_applicable and scores are null. No risk is fabricated.
def build_scaffold_decision(transaction_id: str, correlation_id: str | None) -> dict:
    engines = [{"transaction_id": transaction_id, "engine": e, "status": "not_applicable",
                "risk_score": None, "reason_codes": ["ENGINES_NOT_IMPLEMENTED"],
                "evidence": [], "processing_ms": 0, "engine_version": "m2-scaffold",
                "degraded": True} for e in ("rules", "ml", "graph")]
    return {"decision_id": str(uuid.uuid4()), "transaction_id": transaction_id,
            "decision": "FLAG", "combined_risk_score": None, "fraud_risk_score": None,
            "aml_risk_score": None, "engine_results": engines,
            "reason_codes": ["ENGINES_NOT_IMPLEMENTED", "M2_PERSISTENCE_SCAFFOLD"],
            "model_versions": {}, "policy_version": "m2-scaffold-v0",
            "feature_version": "none", "degraded": True,
            "missing_features": ["rules", "ml", "graph"], "correlation_id": correlation_id,
            "processing_ms": 0, "idempotent_replay": False,
            "decision_basis": "persistence_scaffold", "investigation_status": "pending"}
