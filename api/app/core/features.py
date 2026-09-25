"""Feature builder shared by offline training and online inference (plan B2.1).

Demand model: one row = (route, direction, stop group, 15-minute band) seen
from a "now" band; target = boardings in that group-band.
Travel-time model: one row = (route, direction, segment, 15-minute band);
target = mean running time in seconds.
"""
from __future__ import annotations

import numpy as np

from .demand import DemandModel
from .network import Network
from .traveltime import TravelTime

BAND_MIN = 15
N_BANDS_DAY = 24 * 60 // BAND_MIN
N_GROUPS = 3
LAG_BANDS = 4                    # 60 minutes of recent boardings

DEMAND_FEATURES = [
    "route_code", "direction", "stop_group", "band", "dow", "is_holiday", "rain_mm", "temp_c",
    "event_factor", "horizon", "base_target", "lag_60", "typical_lag_60",
]
DEMAND_CATEGORICAL = ["route_code", "stop_group"]

TT_FEATURES = [
    "route_code", "direction", "seg_idx", "seg_km", "band", "dow", "rain_mm", "recent_speed_ratio",
]
TT_CATEGORICAL = ["route_code"]


def route_codes(net: Network) -> dict[str, int]:
    return {rid: i for i, rid in enumerate(sorted(net.routes))}


def stop_groups(n_stops: int) -> np.ndarray:
    """Split a trip's stops into N_GROUPS contiguous groups (start / middle / end)."""
    return np.minimum((np.arange(n_stops) * N_GROUPS) // n_stops, N_GROUPS - 1)


class BaseDemand:
    """Expected boardings per (route, direction, group, band) on a normal weekday
    with no rain and no event. Used as the calendar baseline feature."""

    def __init__(self, net: Network, dm: DemandModel):
        self.net, self.dm = net, dm
        self.table: dict[tuple[str, int], np.ndarray] = {}
        for rid, r in net.routes.items():
            groups = stop_groups(len(r.stop_ids))
            for d in (0, 1):
                arr = np.zeros((N_GROUPS, N_BANDS_DAY))
                for b in range(N_BANDS_DAY):
                    rate = dm.board_rate(rid, d, b * BAND_MIN + BAND_MIN / 2)
                    arr[:, b] = np.bincount(groups, weights=rate * BAND_MIN, minlength=N_GROUPS)
                self.table[rid, d] = arr

    def get(self, route_id: str, direction: int, group: int, band: int) -> float:
        return float(self.table[route_id, direction][group, band % N_BANDS_DAY])

    def lag(self, route_id: str, direction: int, group: int, now_band: int) -> float:
        arr = self.table[route_id, direction][group]
        return float(sum(arr[(now_band - k) % N_BANDS_DAY] for k in range(1, LAG_BANDS + 1)))


def event_factor(dm: DemandModel, events: list[dict], route_id: str, direction: int, group: int, band: int) -> float:
    """Ratio of expected boardings with planned events vs without, for one group-band."""
    if not events:
        return 1.0
    minute = band * BAND_MIN + BAND_MIN / 2
    base = dm.board_rate(route_id, direction, minute)
    ev = dm.board_rate(route_id, direction, minute, events=events)
    mask = stop_groups(len(base)) == group
    b = base[mask].sum()
    return float(ev[mask].sum() / b) if b > 0 else 1.0


def demand_matrix(cols: dict[str, np.ndarray]) -> np.ndarray:
    return np.column_stack([np.asarray(cols[f], dtype=float) for f in DEMAND_FEATURES])


def tt_matrix(cols: dict[str, np.ndarray]) -> np.ndarray:
    return np.column_stack([np.asarray(cols[f], dtype=float) for f in TT_FEATURES])


def tt_norm_s(tt: TravelTime, route_id: str, direction: int, band: int) -> np.ndarray:
    """Physical norm per segment for a band (used for recent_speed_ratio)."""
    return tt.seg_times_s(route_id, direction, band * BAND_MIN + BAND_MIN / 2)
