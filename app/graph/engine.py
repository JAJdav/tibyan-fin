"""Real-time graph detection (NetworkX, incremental, event-time windowed)."""
from __future__ import annotations
import logging, time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
import networkx as nx
from .. import config

logger = logging.getLogger(__name__)


class RealtimeGraphEngine:
    """record() mutates state; evaluate() is read-only and runs inline on the
    event loop (no await inside -> atomic, no lock). A scoring timeout therefore
    cannot lose graph edges."""
    ENGINE_VERSION = "nx-realtime-v1"

    def __init__(self, window_hours=None, max_nodes=200_000):
        self.graph = nx.Graph()
        self.window = timedelta(hours=window_hours or config.SHARED_INDEX_HOURS)
        self.max_nodes = max_nodes
        self.pruned_edges = 0
        self.truncated = False

    @staticmethod
    def _now(features):
        raw = features.get("timestamp")
        now = datetime.fromisoformat(raw) if raw else datetime.now(timezone.utc)
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)

    def _prune_node(self, node, now):
        if not self.graph.has_node(node):
            return
        stale = [nb for nb in self.graph.neighbors(node)
                 if now - self.graph[node][nb]["ts"] > self.window]
        for nb in stale:
            self.graph.remove_edge(node, nb)
            self.pruned_edges += 1
        for nb in stale:
            if self.graph.degree(nb) == 0:
                self.graph.remove_node(nb)

    def _touch(self, a, b, now):
        if self.graph.has_edge(a, b):
            self.graph[a][b]["ts"] = now
        else:
            self.graph.add_edge(a, b, ts=now)

    def record(self, features: Dict[str, Any]) -> None:
        dev = features.get("device_id")
        if not dev:
            return
        if self.graph.number_of_nodes() >= self.max_nodes:
            self.truncated = True
            return
        cust, acct, mer = (features.get("customer_id"),
                           features.get("account_id"), features.get("merchant_id"))
        now = self._now(features)
        g = self.graph
        for n, kind in ((cust, "customer"), (acct, "account"), (dev, "device"), (mer, "merchant")):
            if n and not g.has_node(n):
                g.add_node(n, kind=kind)
        self._prune_node(dev, now)
        if mer:
            self._prune_node(mer, now)
        if acct: self._touch(acct, dev, now)
        if cust and acct: self._touch(cust, acct, now)
        if mer: self._touch(mer, dev, now)

    async def evaluate(self, features: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.perf_counter()
        tx_id = features.get("transaction_id", "UNKNOWN")
        dev, mer = features.get("device_id"), features.get("merchant_id")
        hrs = int(self.window.total_seconds() // 3600)

        def done(status, score, reasons, evidence, details=None):
            return {"transaction_id": tx_id, "engine": "graph", "status": status,
                    "risk_score": score, "reason_codes": reasons, "evidence": evidence,
                    "engine_version": self.ENGINE_VERSION, "details": details or {},
                    "processing_ms": round((time.perf_counter() - t0) * 1000, 3)}

        if not dev:
            return done("not_applicable", None, [], [], {"reason": "no device_id supplied"})
        g = self.graph
        if not g.has_node(dev):
            return done("not_applicable", None, [], [], {"reason": "device absent from graph"})

        aod = sum(1 for nb in g.neighbors(dev) if g.nodes[nb].get("kind") == "account")
        dom = (sum(1 for nb in g.neighbors(mer) if g.nodes[nb].get("kind") == "device")
               if mer and g.has_node(mer) else 0)

        score, reasons, evidence = 0.0, [], []
        if aod > 3:
            score = min(1.0, 0.5 + (aod - 3) * 0.1)
            reasons.append("DEVICE_SHARED_MANY_ACCOUNTS")
            evidence.append(f"device {dev} linked to {aod} accounts within {hrs}h")
        if dom > 10:
            score = min(1.0, score + 0.15)
            reasons.append("MERCHANT_HIGH_DEVICE_FANIN")
            evidence.append(f"merchant {mer} seen from {dom} devices")

        return done("completed", round(score, 4), reasons, evidence,
                    {"accounts_on_device": aod, "devices_on_merchant": dom,
                     "graph_nodes": g.number_of_nodes(), "window_hours": hrs,
                     "truncated": self.truncated})