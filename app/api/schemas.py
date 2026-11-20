import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TransactionSubmission(BaseModel):
    model_config = ConfigDict(extra="allow")

    transaction_id: str = Field(min_length=1, max_length=64)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    event_time: datetime
    customer_id: str | None = Field(default=None, max_length=64)
    merchant_id: str | None = Field(default=None, max_length=64)
    account_id: str | None = Field(default=None, max_length=64)
    device_id: str | None = Field(default=None, max_length=64)
    counterparty_account_id: str | None = Field(default=None, max_length=64)
    direction: str | None = Field(default=None, max_length=16)
    channel: str | None = Field(default=None, max_length=32)
    metadata: dict = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        v = v.upper()
        if not v.isalpha():
            raise ValueError("currency must be alphabetic")
        return v

    @field_validator("event_time")
    @classmethod
    def _event_time(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)


def canonical_hash(payload: TransactionSubmission) -> str:
    data = payload.model_dump(mode="json")
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class EngineResult(BaseModel):
    transaction_id: str
    engine: Literal["rules", "ml", "graph"]
    status: Literal["completed", "failed", "timeout", "not_applicable"]
    risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    reason_codes: list[str] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)
    processing_ms: int = 0
    engine_version: str = "unknown"
    degraded: bool = False

    @model_validator(mode="after")
    def _score_presence(self):
        if self.status == "completed" and self.risk_score is None:
            raise ValueError("completed result requires risk_score")
        if self.status != "completed" and self.risk_score is not None:
            raise ValueError("non-completed result must not carry risk_score")
        return self


class TransactionDecisionResponse(BaseModel):
    transaction_id: str
    decision_id: str | None = None
    decision: str
    combined_risk_score: float | None = None
    fraud_risk_score: float | None = None
    aml_risk_score: float | None = None
    engine_results: list[dict] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    model_versions: dict = Field(default_factory=dict)
    policy_version: str
    feature_version: str
    degraded: bool = False
    missing_features: list[str] = Field(default_factory=list)
    correlation_id: str | None = None
    processing_ms: int = 0
    idempotent_replay: bool = False
    decision_basis: str | None = None
    investigation_status: str | None = None
