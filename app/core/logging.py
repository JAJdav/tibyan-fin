import json
import logging
from datetime import datetime, timezone

from app.core.config import settings


def configure_logging() -> None:
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                        format="%(message)s")


def log_event(event: str, **fields) -> None:
    payload = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
               "event": event, **fields}
    logging.getLogger("fraud_aml").info(json.dumps(payload, default=str))
