"""Physical travel-time norms: segment running times from distance and the
hourly speed profile. Used by the simulator, the synthetic data generator and
as the fallback when the LightGBM travel-time model is missing."""
from __future__ import annotations

import math

import numpy as np

from .network import Network


class TravelTime:
    def __init__(self, net: Network):
        self.net = net
        p = net.demand_params["travel_time"]
        self.speed = np.asarray(p["speed_kmh_by_hour"], dtype=float)
        self.dwell_per_board = float(p["dwell_s_per_boarding"])
        self.dwell_min = float(p["dwell_s_min"])
        self.noise_cv = float(p["noise_cv"])
        w = net.demand_params["weather"]
        self.rain_breaks = w["rain_mm_breaks"]
        self.rain_speed = w["speed_factor"]

    def speed_kmh(self, minute: float) -> float:
        x = (minute / 60.0) - 0.5
        h0 = int(math.floor(x)) % 24
        f = x - math.floor(x)
        return float((1 - f) * self.speed[h0] + f * self.speed[(h0 + 1) % 24])

    def rain_speed_factor(self, rain_mm: float) -> float:
        return float(self.rain_speed[int(np.searchsorted(self.rain_breaks, rain_mm, side="right"))])

    def seg_times_s(self, route_id: str, direction: int, minute: float, speed_factor: float = 1.0) -> np.ndarray:
        """Running time (s) of each segment, excluding dwell."""
        km = self.net.routes[route_id].seg_km(direction)
        return km / (self.speed_kmh(minute) * speed_factor) * 3600.0

    def run_time_min(self, route_id: str, direction: int, minute: float, speed_factor: float = 1.0) -> float:
        n_stops = len(self.net.routes[route_id].stop_ids)
        dwell = self.dwell_min * (n_stops - 2)
        return (self.seg_times_s(route_id, direction, minute, speed_factor).sum() + dwell) / 60.0

    def cycle_min(self, route_id: str, minute: float, speed_factor: float = 1.0) -> float:
        return (
            self.run_time_min(route_id, 0, minute, speed_factor)
            + self.run_time_min(route_id, 1, minute, speed_factor)
            + 2 * self.net.layover_min
        )

    def dwell_s(self, boardings: float, alightings: float = 0.0) -> float:
        return max(self.dwell_min, self.dwell_per_board * max(boardings, alightings * 0.6))
