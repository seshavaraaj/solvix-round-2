"""Rider crowding reports (plan B6.2–B6.3, solution2 §6.3).

Reports are the one real (non-synthetic) demand signal. Each report nudges
the load estimate toward its level, weighted by count and recency
(exponential decay, 15-minute half-life). Influence is capped at ±30% of the
model estimate so a few taps cannot swamp the model.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

HALF_LIFE_S = 15 * 60
CAP = 0.30
MAX_AGE_S = 2 * 3600
RATE_LIMIT_S = 5 * 60
LEVEL_LF = {"crowded": 1.2, "ok": 0.7, "empty": 0.25}


@dataclass
class Report:
    device_id: str
    bus_id: str
    route_id: str
    level: str
    received_ts: float           # wall-clock seconds


def blend(model_lf: float, reports: list[Report], now_ts: float) -> float:
    """Blend a model load factor with reports; result stays within ±CAP of the model."""
    if not reports:
        return model_lf
    ws = [0.5 ** (max(0.0, now_ts - r.received_ts) / HALF_LIFE_S) for r in reports]
    w = sum(ws)
    if w <= 1e-6:
        return model_lf
    target = sum(wi * LEVEL_LF[r.level] for wi, r in zip(ws, reports)) / w
    alpha = w / (w + 1.0)
    base = max(model_lf, 0.05)
    value = base + alpha * (target - base)
    return float(min(max(value, base * (1 - CAP)), base * (1 + CAP)))


class CrowdingStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reports: list[Report] = []
        self.last_by_key: dict[tuple[str, str], float] = {}
        self.version = 0

    def load(self, reports: list[Report]) -> None:
        with self._lock:
            self.reports = [r for r in reports if time.time() - r.received_ts < MAX_AGE_S]
            for r in self.reports:
                k = (r.device_id, r.bus_id)
                self.last_by_key[k] = max(self.last_by_key.get(k, 0.0), r.received_ts)
            self.version += 1

    def allowed(self, device_id: str, bus_id: str, now_ts: float | None = None) -> bool:
        now_ts = time.time() if now_ts is None else now_ts
        last = self.last_by_key.get((device_id, bus_id))
        return last is None or now_ts - last >= RATE_LIMIT_S

    def add(self, r: Report) -> None:
        with self._lock:
            self.reports.append(r)
            self.last_by_key[r.device_id, r.bus_id] = r.received_ts
            cutoff = time.time() - MAX_AGE_S
            self.reports = [x for x in self.reports if x.received_ts >= cutoff]
            self.version += 1

    def for_bus(self, bus_id: str) -> list[Report]:
        return [r for r in self.reports if r.bus_id == bus_id]

    def for_route(self, route_id: str) -> list[Report]:
        return [r for r in self.reports if r.route_id == route_id]

    def bus_lf(self, bus_id: str, model_lf: float, now_ts: float | None = None) -> float:
        return blend(model_lf, self.for_bus(bus_id), time.time() if now_ts is None else now_ts)

    def route_scale(self, route_id: str, model_lf: float, now_ts: float | None = None) -> float:
        """Multiplier for the route's forecast loads (1.0 when no reports)."""
        reps = self.for_route(route_id)
        if not reps:
            return 1.0
        base = max(model_lf, 0.05)
        return blend(base, reps, time.time() if now_ts is None else now_ts) / base
