"""In-memory idempotency store (Stage 1 foundation).

Contract:
  * same transaction_id + same payload  -> replay the stored response, no reprocessing
  * same transaction_id + different payload -> conflict (client bug or tampering)
  * same transaction_id while first request is still running -> in_progress

Limitation: state is lost on restart. The MySQL idempotency_records table replaces
this in the database stage; the interface below is kept small so the swap is easy.
"""
import hashlib
import json
import threading
from typing import Optional


def payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class IdempotencyStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._records: dict[str, dict] = {}

    def begin(self, tx_id: str, p_hash: str) -> tuple[str, Optional[dict]]:
        """Returns (state, stored_response). state: new | replay | conflict | in_progress."""
        with self._lock:
            rec = self._records.get(tx_id)
            if rec is None:
                self._records[tx_id] = {"hash": p_hash, "response": None}
                return "new", None
            if rec["hash"] != p_hash:
                return "conflict", None
            if rec["response"] is None:
                return "in_progress", None
            return "replay", rec["response"]

    def complete(self, tx_id: str, response: dict) -> None:
        with self._lock:
            self._records[tx_id]["response"] = response

    def abort(self, tx_id: str) -> None:
        """Release a reservation when processing failed, so the client can retry."""
        with self._lock:
            rec = self._records.get(tx_id)
            if rec and rec["response"] is None:
                del self._records[tx_id]

    def get(self, tx_id: str) -> Optional[dict]:
        with self._lock:
            rec = self._records.get(tx_id)
            return rec["response"] if rec else None

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)
