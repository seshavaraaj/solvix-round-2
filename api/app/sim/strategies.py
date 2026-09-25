"""Strategies and scenario set-up for the simulator (plan B5.2–B5.4).

1. baseline      fixed timetable, no control
2. holding       baseline + virtual-schedule holding at the mid-route timepoint
3. transitpulse  headway-based holding + reallocation: the optimiser runs every
                 30 minutes and its recommendations are auto-approved; terminal
                 and mid-route departures are spaced to the current headway
                 (cycle / buses), so buses added or removed are absorbed evenly

Forecast error for the robustness test is injected into what the
TransitPulse planner sees, never into the true demand:
  0 / 0.2 / 0.4   each route's forecast x U(1 - e, 1 + e), redrawn each cycle
  "missed_surge"  the forecast does not know about planned events
"""
from __future__ import annotations

import numpy as np

from ..core.demand import DemandModel
from ..core.network import Network
from ..core.optimise import MAX_CHANGES_PER_HOUR, solve
from ..core.planning import build_problem, route_inputs
from ..core.timeutil import day_type, hhmm_to_s
from ..core.traveltime import TravelTime
from .model import Move, SimConfig, Simulation

P90_OVER_P50 = 1.25
ERROR_LEVELS: list[float | str] = [0, 0.2, 0.4, "missed_surge"]


def make_planner(net: Network, dm: DemandModel, tt: TravelTime, events: list[dict], dtype: str, rain_mm: float,
                 error_level: float | str, seed: int):
    rng = np.random.default_rng(seed + 7919)
    fc_events = [] if error_level == "missed_surge" else events
    e = 0.0 if isinstance(error_level, str) else float(error_level)

    def planner(sim: Simulation, t: float) -> list[Move]:
        mult = {rid: (1.0 + rng.uniform(-e, e)) if e else 1.0 for rid in net.routes}

        def p50(r: str, d: int, m: float) -> np.ndarray:
            return dm.board_rate(r, d, m, dtype, rain_mm, fc_events) * mult[r]

        def p90(r: str, d: int, m: float) -> np.ndarray:
            return p50(r, d, m) * P90_OVER_P50

        fleet = {rid: 0 for rid in net.routes}
        for b in sim.buses:
            if not b.active or b.broken:
                continue
            if b.reassign is None:
                target = b.route_id
            else:
                target = b.reassign[1]          # already committed to its new route (None = depot)
            if target in fleet:
                fleet[target] += 1
        left = {rid: MAX_CHANGES_PER_HOUR for rid in net.routes}
        recent = []
        for mv in sim.moves_done:
            if t - 3600 < mv.at_s <= t:
                recent.append((mv.from_route, mv.to_route))
                for r in (mv.from_route, mv.to_route):
                    if r in left:
                        left[r] -= 1
        inputs = route_inputs(net, dm, tt, t, fleet, p50, p90, speed_factor=sim.speed_factor)
        plan = solve(build_problem(net, inputs, dict(sim.reserve), left, recent), time_limit_s=2.0)
        return [Move(t, a.from_route_id, a.to_route_id, a.bus_count, a.deadhead_km) for a in plan.actions]

    return planner


def scenario_config(net: Network, dm: DemandModel, tt: TravelTime, scenario: str, strategy: str,
                    start_s: float, end_s: float, seed: int, error_level: float | str = 0) -> SimConfig:
    sc = net.scenarios["scenarios"][scenario]
    dtype = day_type(sc["date"], net.config.get("holidays", []))
    events = dm.events_for(sc)
    cfg = SimConfig(
        start_s=start_s, end_s=end_s, day_type=dtype, rain_mm=float(sc["rain_mm"]), events=events,
        breakdowns=[{"route_id": b["route_id"], "at_s": hhmm_to_s(b["at"])} for b in sc.get("breakdowns", [])],
        strategy=strategy, seed=seed,
    )
    if strategy == "transitpulse":
        cfg.planner = make_planner(net, dm, tt, events, dtype, float(sc["rain_mm"]), error_level, seed)
    return cfg
