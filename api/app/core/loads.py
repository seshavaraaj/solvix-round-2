"""Load estimation (solution2 §6.2).

Ticket machines give boardings only. Alightings are assigned with stop
attraction weights and balanced with iterative proportional fitting (IPF).
The same maths turns forecast boarding rates into segment flows and load
factors for detection and the optimiser.
"""
from __future__ import annotations

import numpy as np


def ipf_trip(boardings: np.ndarray, dest_probs: np.ndarray, alight_share: np.ndarray, iters: int = 30) -> np.ndarray:
    """Estimate an origin-destination matrix for one trip.

    boardings    (n,)   observed boardings per stop (trip order)
    dest_probs   (n, n) seed P(alight j | board i), upper triangular
    alight_share (n,)   attraction share per stop used as column margin
    returns      (n, n) OD counts; rows sum to boardings
    """
    b = np.asarray(boardings, dtype=float)
    seed = dest_probs * b[:, None]
    total = b.sum()
    if total <= 0:
        return np.zeros_like(seed)
    cols = alight_share / alight_share.sum() * total if alight_share.sum() > 0 else seed.sum(axis=0)
    m = seed.copy()
    for _ in range(iters):
        rs = m.sum(axis=1)
        m *= np.divide(b, rs, out=np.zeros_like(b), where=rs > 0)[:, None]
        cs = m.sum(axis=0)
        m *= np.divide(cols, cs, out=np.zeros_like(cols), where=cs > 0)[None, :]
    rs = m.sum(axis=1)  # finish on rows so boardings are exact
    m *= np.divide(b, rs, out=np.zeros_like(b), where=rs > 0)[:, None]
    return m


def onboard_from_od(od: np.ndarray) -> np.ndarray:
    """Passengers on board after departing each stop (last entry is 0)."""
    return np.cumsum(od.sum(axis=1)) - np.cumsum(od.sum(axis=0))


def segment_flow(board_rate: np.ndarray, dest_probs: np.ndarray) -> np.ndarray:
    """Passenger flow (pax/min) on each segment i -> i+1 from boarding rates."""
    od = dest_probs * np.asarray(board_rate, dtype=float)[:, None]
    return onboard_from_od(od)[:-1]


def load_factor(flow_per_min: np.ndarray, headway_min: float, capacity: int) -> np.ndarray:
    """Average load factor per segment for buses every `headway_min`."""
    return np.asarray(flow_per_min) * headway_min / capacity
