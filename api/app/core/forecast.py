"""Demand and travel-time inference (plan B2.5). Models load once at start-up.

`Forecaster.view(...)` returns, per route-direction, P50/P90 boardings per
stop group for the next 8 bands (2 hours), plus helpers that turn them into
per-stop boarding rates and segment load factors.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

from .demand import DemandModel
from .features import (BAND_MIN, DEMAND_FEATURES, N_GROUPS, BaseDemand, demand_matrix, event_factor,
                       route_codes, stop_groups, tt_matrix)
from .loads import segment_flow
from .network import Network
from .traveltime import TravelTime

HORIZON_BANDS = 8


@dataclass
class ForecastView:
    now_band: int
    p50: dict[tuple[str, int], np.ndarray]     # (route, dir) -> (N_GROUPS, HORIZON_BANDS) boardings per band
    p90: dict[tuple[str, int], np.ndarray]
    events: list[dict]
    source: str                                  # lightgbm | formula


class Forecaster:
    def __init__(self, net: Network, dm: DemandModel, tt: TravelTime, models_dir: Path):
        self.net, self.dm, self.tt = net, dm, tt
        self.codes = route_codes(net)
        self.base = BaseDemand(net, dm)
        self.m50 = self.m90 = self.mtt = None
        self.loaded = False
        self._ev_cache: dict[tuple, float] = {}
        try:
            import lightgbm as lgb

            self.m50 = lgb.Booster(model_file=str(models_dir / "demand_p50.txt"))
            self.m90 = lgb.Booster(model_file=str(models_dir / "demand_p90.txt"))
            self.mtt = lgb.Booster(model_file=str(models_dir / "traveltime.txt"))
            meta = json.loads((models_dir / "meta.json").read_text(encoding="utf-8"))
            if meta["demand_features"] != DEMAND_FEATURES or meta["route_codes"] != self.codes:
                raise ValueError("model features do not match app.core.features")
            self.loaded = True
        except Exception as exc:  # models missing: fall back to the formula so the demo still runs
            print(f"forecast models not loaded ({exc}); using demand formula")

    # ---- demand ----------------------------------------------------------------------
    def view(self, t_s: float, day: str, day_type_holiday: bool, rain_mm: float, temp_c: float,
             events: list[dict], observed: pl.DataFrame) -> ForecastView:
        """observed: boardings with columns route_id, direction, stop_seq, dep_s, boardings (last 60 min)."""
        now_band = int(t_s // (BAND_MIN * 60))
        dow = date.fromisoformat(day).weekday()
        keys = [(rid, d, g) for rid in sorted(self.net.routes) for d in (0, 1) for g in range(N_GROUPS)]
        lag = {k: 0.0 for k in keys}
        if observed.height:
            for r in observed.iter_rows(named=True):
                g = int(stop_groups(len(self.net.routes[r["route_id"]].stop_ids))[r["stop_seq"]])
                lag[r["route_id"], int(r["direction"]), g] += float(r["boardings"])
        cols = {f: [] for f in DEMAND_FEATURES}
        for h in range(1, HORIZON_BANDS + 1):
            band = now_band + h
            for rid, d, g in keys:
                cols["route_code"].append(self.codes[rid])
                cols["direction"].append(d)
                cols["stop_group"].append(g)
                cols["band"].append(band)
                cols["dow"].append(dow)
                cols["is_holiday"].append(1.0 if day_type_holiday else 0.0)
                cols["rain_mm"].append(rain_mm)
                cols["temp_c"].append(temp_c)
                cols["event_factor"].append(self._event_factor(events, rid, d, g, band))
                cols["horizon"].append(h)
                cols["base_target"].append(self.base.get(rid, d, g, band))
                cols["lag_60"].append(lag[rid, d, g])
                cols["typical_lag_60"].append(self.base.lag(rid, d, g, now_band + 1))
        X = demand_matrix({k: np.asarray(v) for k, v in cols.items()})
        if self.loaded:
            y50 = np.maximum(self.m50.predict(X), 0.0)
            y90 = np.maximum(self.m90.predict(X), y50)
            source = "lightgbm"
        else:
            base = X[:, DEMAND_FEATURES.index("base_target")] * X[:, DEMAND_FEATURES.index("event_factor")]
            y50, y90, source = base, base * 1.3, "formula"
        p50: dict[tuple[str, int], np.ndarray] = {}
        p90: dict[tuple[str, int], np.ndarray] = {}
        n = len(keys)
        for i, (rid, d, g) in enumerate(keys):
            p50.setdefault((rid, d), np.zeros((N_GROUPS, HORIZON_BANDS)))[g] = y50[i::n]
            p90.setdefault((rid, d), np.zeros((N_GROUPS, HORIZON_BANDS)))[g] = y90[i::n]
        return ForecastView(now_band, p50, p90, events, source)

    def _event_factor(self, events: list[dict], rid: str, d: int, g: int, band: int) -> float:
        if not events:
            return 1.0
        key = (json.dumps(events, sort_keys=True), rid, d, g, band)
        if key not in self._ev_cache:
            self._ev_cache[key] = event_factor(self.dm, events, rid, d, g, band)
        return self._ev_cache[key]

    def stop_rates(self, v: ForecastView, route_id: str, direction: int, minute: float, quantile: str = "p50") -> np.ndarray:
        """Boardings per minute per stop for the band containing `minute`."""
        h = int(minute // BAND_MIN) - v.now_band
        h = min(max(h, 1), HORIZON_BANDS) - 1
        groups = (v.p50 if quantile == "p50" else v.p90)[route_id, direction][:, h]
        shape = self.dm.board_rate(route_id, direction, minute, events=v.events)
        gid = stop_groups(len(shape))
        out = np.zeros_like(shape)
        for g in range(N_GROUPS):
            mask = gid == g
            tot = shape[mask].sum()
            if tot > 0:
                out[mask] = shape[mask] / tot * groups[g] / BAND_MIN
            elif mask.any():
                out[mask] = groups[g] / BAND_MIN / mask.sum()
        return out

    def segment_loads(self, v: ForecastView, route_id: str, direction: int, headway_min: float,
                      scale: float = 1.0, bands: int = 4) -> tuple[np.ndarray, np.ndarray]:
        """(P50, P90) load factor per (band, segment) for the next `bands` bands."""
        lf50, lf90 = [], []
        for h in range(1, bands + 1):
            minute = (v.now_band + h) * BAND_MIN + BAND_MIN / 2
            dest = self.dm.dest_probs(route_id, direction, minute)
            f50 = segment_flow(self.stop_rates(v, route_id, direction, minute, "p50"), dest)
            f90 = segment_flow(self.stop_rates(v, route_id, direction, minute, "p90"), dest)
            lf50.append(f50 * headway_min / self.net.capacity * scale)
            lf90.append(f90 * headway_min / self.net.capacity * scale)
        return np.array(lf50), np.array(lf90)

    # ---- travel time -----------------------------------------------------------------
    def segment_times(self, route_id: str, direction: int, t_s: float, day: str, rain_mm: float,
                      recent_ratio: float = 1.0) -> np.ndarray:
        """Predicted running time (s) per segment for the band containing t_s."""
        band = int(t_s // (BAND_MIN * 60))
        km = self.net.routes[route_id].seg_km(direction)
        if not self.loaded:
            return self.tt.seg_times_s(route_id, direction, t_s / 60, self.tt.rain_speed_factor(rain_mm)) * recent_ratio
        n = len(km)
        X = tt_matrix({
            "route_code": np.full(n, self.codes[route_id]), "direction": np.full(n, direction),
            "seg_idx": np.arange(n), "seg_km": km, "band": np.full(n, band),
            "dow": np.full(n, date.fromisoformat(day).weekday()), "rain_mm": np.full(n, rain_mm),
            "recent_speed_ratio": np.full(n, recent_ratio),
        })
        return np.maximum(self.mtt.predict(X), 10.0)
