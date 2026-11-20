"""Tiny in-process metrics for the demo. Prometheus replaces this in a later stage."""
import threading
from collections import Counter, deque


class Metrics:
    def __init__(self, window: int = 1000):
        self._lock = threading.Lock()
        self._counters: Counter = Counter()
        self._latencies = deque(maxlen=window)

    def inc(self, name: str, n: int = 1) -> None:
        with self._lock:
            self._counters[name] += n

    def observe_ms(self, ms: float) -> None:
        with self._lock:
            self._latencies.append(ms)

    def snapshot(self) -> dict:
        with self._lock:
            lat = sorted(self._latencies)
            counters = dict(self._counters)

        def pct(p):
            return round(lat[min(len(lat) - 1, int(len(lat) * p))], 3) if lat else None

        return {
            "counters": counters,
            "latency_ms": {"samples": len(lat), "p50": pct(0.50), "p95": pct(0.95), "p99": pct(0.99)},
            "note": "In-process, resets on restart. Not a benchmark.",
        }
