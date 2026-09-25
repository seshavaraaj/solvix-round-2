"""Synthetic demand formula (solution2 §6.3), shared by the offline generator,
the simulator and the load estimator.

boardings per stop per minute =
    base_rate(route, stop, direction) x tod(minute) x day_type x weather x event
"""
from __future__ import annotations

import math

import numpy as np

from .network import Network
from .traveltime import TravelTime


class DemandModel:
    def __init__(self, net: Network, tt: TravelTime):
        self.net = net
        p = net.demand_params
        self.params = p
        tod = np.asarray(p["tod_profile"], dtype=float)
        self.tod = tod / tod.sum()                      # share of the day per hour
        self.type_w = p["stop_type_weight"]
        self.bias = float(p.get("evening_residential_bias", 1.0))
        self.day_type_f = p["day_type"]
        self.rain_breaks = p["weather"]["rain_mm_breaks"]
        self.rain_demand = p["weather"]["demand_factor"]
        self.daily_total: dict[str, float] = {}
        for r in net.routes.values():
            buses = math.ceil(tt.cycle_min(r.id, 18 * 60) / r.planned_headway_min)
            self.daily_total[r.id] = float(p["pax_per_bus_day"]) * buses * r.busy_factor

    # ---- factors -----------------------------------------------------------
    def tod_share_per_min(self, minute: float) -> float:
        """Share of daily boardings per minute, linearly interpolated between hour centres."""
        x = (minute / 60.0) - 0.5
        h0 = int(math.floor(x)) % 24
        f = x - math.floor(x)
        return float((1 - f) * self.tod[h0] + f * self.tod[(h0 + 1) % 24]) / 60.0

    def rain_factor(self, rain_mm: float) -> float:
        return float(self.rain_demand[int(np.searchsorted(self.rain_breaks, rain_mm, side="right"))])

    def _weights(self, route_id: str, direction: int, minute: float) -> tuple[np.ndarray, np.ndarray]:
        """Boarding and alighting weights per stop in trip order."""
        r = self.net.routes[route_id]
        types = [self.net.stops[s].type for s in r.stops(direction)]
        hour = minute / 60.0
        board = np.array([self.type_w[t] for t in types], dtype=float)
        alight = board.copy()
        evening, morning = 16 <= hour < 21, 6 <= hour < 11
        for i, t in enumerate(types):
            if evening and t in ("commercial", "hub"):
                board[i] *= self.bias
            if evening and t == "residential":
                alight[i] *= self.bias
            if morning and t == "residential":
                board[i] *= self.bias
            if morning and t in ("commercial", "hub"):
                alight[i] *= self.bias
        board[-1] = 0.0          # nobody boards at the last stop
        alight[0] = 0.0          # nobody alights at the first stop
        return board, alight

    # ---- public API ----------------------------------------------------------
    def board_rate(
        self,
        route_id: str,
        direction: int,
        minute: float,
        day_type: str = "weekday",
        rain_mm: float = 0.0,
        events: list[dict] | tuple = (),
        multiplier: float = 1.0,
    ) -> np.ndarray:
        """Expected boardings per minute at each stop of a trip in `direction`."""
        board, _ = self._weights(route_id, direction, minute)
        # both directions share the route total; weights normalised across both
        b0, _ = self._weights(route_id, 0, minute)
        b1, _ = self._weights(route_id, 1, minute)
        norm = b0.sum() + b1.sum()
        rate = self.daily_total[route_id] * self.tod_share_per_min(minute) * board / norm
        rate *= self.day_type_f.get(day_type, 1.0) * self.rain_factor(rain_mm) * multiplier
        stops = self.net.routes[route_id].stops(direction)
        for ev in events:
            if ev["start_min"] <= minute < ev["end_min"]:
                for i, s in enumerate(stops):
                    if s in ev["stops"] and i < len(stops) - 1:
                        rate[i] *= float(ev["factor"])
        return rate

    def dest_probs(self, route_id: str, direction: int, minute: float) -> np.ndarray:
        """P(alight at j | board at i), upper-triangular, rows sum to 1 (last row 0)."""
        _, alight = self._weights(route_id, direction, minute)
        n = len(alight)
        m = np.zeros((n, n))
        for i in range(n - 1):
            w = alight[i + 1:].copy()
            # short trips a little more likely than long ones
            w *= np.exp(-0.08 * np.arange(len(w)))
            m[i, i + 1:] = w / w.sum()
        return m

    def events_for(self, scenario: dict) -> list[dict]:
        from .timeutil import hhmm_to_s

        return [
            {"stops": ev["stops"], "start_min": hhmm_to_s(ev["start"]) / 60, "end_min": hhmm_to_s(ev["end"]) / 60,
             "factor": ev["factor"]}
            for ev in scenario.get("events", [])
        ]
