"""Builds optimiser inputs from a demand view. Shared by the API cycle (which
uses the LightGBM forecast) and the simulator's TransitPulse strategy (which
uses the demand formula plus injected forecast error)."""
from __future__ import annotations

from typing import Callable

import numpy as np

from .demand import DemandModel
from .loads import segment_flow
from .network import Network
from .optimise import BAND_MIN, N_BANDS, Problem, RouteInput
from .traveltime import TravelTime

# rates(route_id, direction, minute) -> boardings per minute per stop
RateFn = Callable[[str, int, float], np.ndarray]


def route_inputs(
    net: Network,
    dm: DemandModel,
    tt: TravelTime,
    t_s: float,
    fleet: dict[str, int],
    rate_p50: RateFn,
    rate_p90: RateFn,
    speed_factor: float = 1.0,
    duty_ok: dict[str, int] | None = None,
    load_scale: dict[str, float] | None = None,
) -> list[RouteInput]:
    out = []
    for rid, r in net.routes.items():
        if fleet.get(rid, 0) <= 0:
            continue
        b50, f50, f90 = [], [], []
        scale = (load_scale or {}).get(rid, 1.0)
        for b in range(N_BANDS):
            minute = t_s / 60 + BAND_MIN * b + BAND_MIN / 2
            tot, fl50, fl90 = 0.0, 0.0, 0.0
            for d in (0, 1):
                dest = dm.dest_probs(rid, d, minute)
                r50 = rate_p50(rid, d, minute)
                r90 = rate_p90(rid, d, minute)
                tot += float(r50.sum())
                fl50 = max(fl50, float(segment_flow(r50, dest).max()))
                fl90 = max(fl90, float(segment_flow(r90, dest).max()))
            b50.append(tot)
            f50.append(fl50 * scale)
            f90.append(fl90 * scale)
        out.append(RouteInput(
            route_id=rid, depot_id=r.depot_id, n_buses=fleet[rid],
            cycle_min=tt.cycle_min(rid, t_s / 60, speed_factor),
            min_headway_min=r.min_headway_min, board_p50=b50, flow_p50=f50, flow_p90=f90,
            duty_ok=(duty_ok or {}).get(rid), capacity=net.capacity,
        ))
    return out


def build_problem(
    net: Network,
    inputs: list[RouteInput],
    reserve: dict[str, int],
    moves_left: dict[str, int] | None = None,
    recent: list[tuple[str | None, str | None]] | None = None,
) -> Problem:
    """recent: (from_route, to_route) of changes in the last hour; blocks reversals."""
    ids = [r.route_id for r in inputs]
    dh: dict[tuple[str | None, str | None], float] = {}
    for a in ids:
        dh[None, a] = net.route_deadhead_km(None, a)
        dh[a, None] = net.route_deadhead_km(a, None)
        for c in ids:
            if a != c:
                dh[a, c] = net.route_deadhead_km(a, c)
    recent = recent or []
    return Problem(routes=inputs, reserve=reserve, deadhead_km=dh,
                   deadhead_speed_kmh=float(net.config["deadhead_speed_kmh"]), moves_left=moves_left,
                   no_donate={c for _, c in recent if c}, no_receive={a for a, _ in recent if a})


def expected_effect(inp: RouteInput, n_after: int) -> dict:
    """Wait (headway / 2) and P90 peak load before vs after a fleet change."""
    h0 = inp.cycle_min / max(1, inp.n_buses)
    h1 = inp.cycle_min / max(1, n_after)
    peak = max(inp.flow_p90) if inp.flow_p90 else 0.0
    return {
        "wait_min_before": round(h0 / 2, 1),
        "wait_min_after": round(h1 / 2, 1),
        "peak_load_before": round(peak * h0 / inp.capacity, 2),
        "peak_load_after": round(peak * h1 / inp.capacity, 2),
    }
