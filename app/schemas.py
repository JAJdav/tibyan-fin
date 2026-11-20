"""Request validation. Anything that fails here never reaches feature or rule code."""
import ipaddress
import re
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import config

ID_RE = re.compile(r"^[A-Za-z0-9_\-:.]{1,64}$")
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
COUNTRY_RE = re.compile(r"^[A-Z]{2}$")

Channel = Literal["card_present", "card_not_present", "mobile", "web", "atm", "wire", "other"]


class TransactionIn(BaseModel):
    # extra="forbid": unknown fields are an error, so typos in n8n mappings are caught early.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    transaction_id: str
    customer_id: str
    account_id: str
    merchant_id: str
    amount: float = Field(gt=0, le=1_000_000_000)
    currency: str
    timestamp: datetime
    device_id: Optional[str] = None
    channel: Optional[Channel] = None
    country: Optional[str] = None
    merchant_category: Optional[str] = Field(default=None, max_length=64)
    ip_address: Optional[str] = None

    @field_validator("transaction_id", "customer_id", "account_id", "merchant_id", "device_id")
    @classmethod
    def _check_id(cls, v):
        if v is None:
            return v
        if not ID_RE.match(v):
            raise ValueError("must be 1-64 chars of letters, digits, '_', '-', ':' or '.'")
        return v

    @field_validator("currency")
    @classmethod
    def _check_currency(cls, v):
        v = v.upper()
        if not CURRENCY_RE.match(v):
            raise ValueError("must be a 3-letter ISO 4217 code, e.g. SAR")
        return v

    @field_validator("country")
    @classmethod
    def _check_country(cls, v):
        if v is None:
            return v
        v = v.upper()
        if not COUNTRY_RE.match(v):
            raise ValueError("must be a 2-letter ISO 3166 code, e.g. SA")
        return v

    @field_validator("ip_address")
    @classmethod
    def _check_ip(cls, v):
        if v is None:
            return v
        try:
            ipaddress.ip_address(v)
        except ValueError:
            raise ValueError("must be a valid IPv4 or IPv6 address")
        return v

    @field_validator("timestamp")
    @classmethod
    def _check_timestamp(cls, v: datetime):
        # Naive timestamps are treated as UTC; everything is normalised to UTC.
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        v = v.astimezone(timezone.utc)
        limit = datetime.now(timezone.utc) + timedelta(seconds=config.MAX_FUTURE_SKEW_SECONDS)
        if v > limit:
            raise ValueError("timestamp is in the future")
        return v
