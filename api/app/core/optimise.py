"""Fleet reallocation optimiser (solution2 §6.6), OR-Tools CP-SAT.

Decisions: headway per route and 30-minute band from HEADWAYS, and whole
buses moved donor -> receiver, from the depot reserve (add_trip) or back to
the depot (release_bus).

Objective (minimise, all in passenger-minutes):
  waiting        demand x headway / 2
  overcrowding   passengers above rated capacity x OVERCROWD_W
  reserve use    ADD_W per extra bus per band (drivers and fuel are not free)
  release        -RELEASE_W per bus sent back to the depot per band
  deadhead       km x DEADHEAD_W
  stability      MOVE_BUS_W per moved bus, MOVE_W per action, CHANGE_W per headway change
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

HEADWAYS = (6, 8, 10, 12, 15, 20)
BAND_MIN = 30
N_BANDS = 3                   # 90-minute recommendation window
OVERCROWD_W = 8.0
ADD_W = 300.0
RELEASE_W = 120.0
DEADHEAD_W = 15.0
CHANGE_W = 20.0
MOVE_W = 60.0
MOVE_BUS_W = 200.0
MAX_DEADHEAD_MIN = 30.0       # a moved bus must reach its new route within one band
RECEIVE_P90_LF = 0.9          # only routes near capacity may receive buses (overcrowding trigger)
DONATE_P50_LF = 0.5           # only lightly loaded routes may give buses
RELEASE_P90_LF = 0.3          # only underused routes may release buses to the depot
MAX_CHANGES_PER_HOUR = 2
MAX_BUSES_PER_ACTION = 3
SCALE = 10                    # CP-SAT needs integer coefficients


@dataclass
class RouteInput:
    route_id: str
    depot_id: str
    n_buses: int                   # buses currently in service on the route
    cycle_min: float
    min_headway_min: float         # service guarantee: headway may not exceed this
    board_p50: list[float]         # boardings per minute, both directions, per band
    flow_p50: list[float]          # peak-segment flow (pax/min) per band, P50
    flow_p90: list[float]          # peak-segment flow (pax/min) per band, P90
    duty_ok: int | None = None     # buses whose driver can work the whole window
    capacity: int = 60

    def headway_now(self) -> float:
        return self.cycle_min / max(1, self.n_buses)

    def options(self) -> list[float]:
        """Allowed headways: the fixed list within the service guarantee, plus
        cycle / k for bus counts near today's (whole buses give finer steps than
        the list), plus the status quo so today's plan is always feasible."""
        opts = {float(h) for h in HEADWAYS if h <= self.min_headway_min}
        for k in range(max(1, self.n_buses - 4), self.n_buses + 7):
            h = round(float(self.cycle_min / k), 2)
            if HEADWAYS[0] <= h <= self.min_headway_min:
                opts.add(h)
        opts.add(round(float(self.headway_now()), 2))
        return sorted(opts)

    def option_now(self) -> float:
        return round(float(self.headway_now()), 2)

    def buses_for(self, h: float) -> int:
        # tolerance: option headways are rounded to 0.01 min
        return math.ceil(self.cycle_min / h - 0.02)

    def peak_lf(self, flows: list[float]) -> float:
        return max(flows) * self.headway_now() / self.capacity if flows else 0.0

    @property
    def can_receive(self) -> bool:
        return self.peak_lf(self.flow_p90) >= RECEIVE_P90_LF

    @property
    def can_donate(self) -> bool:
        return self.peak_lf(self.flow_p50) < DONATE_P50_LF and not self.can_receive

    @property
    def can_release(self) -> bool:
        return self.peak_lf(self.flow_p90) < RELEASE_P90_LF


@dataclass
class Action:
    action: str                    # move_bus | add_trip | release_bus
    from_route_id: str | None
    to_route_id: str | None
    bus_count: int
    deadhead_km: float


@dataclass
class Plan:
    solver: str                    # cp_sat | greedy
    status: str
    actions: list[Action] = field(default_factory=list)
    headways: dict[str, list[float]] = field(default_factory=dict)
    fleet_after: dict[str, int] = field(default_factory=dict)
    objective: float = 0.0
    runtime_s: float = 0.0


@dataclass
class Problem:
    routes: list[RouteInput]
    reserve: dict[str, int]                       # usable reserve buses per depot
    deadhead_km: dict[tuple[str | None, str | None], float]   # (from, to) -> km; None = depot
    deadhead_speed_kmh: float = 20.0
    moves_left: dict[str, int] | None = None      # remaining move actions per route this hour
    no_donate: set[str] = field(default_factory=set)    # received buses in the last hour: no reversal
    no_receive: set[str] = field(default_factory=set)   # gave buses in the last hour

    def may_move(self, a: RouteInput, c: RouteInput) -> bool:
        return (a.can_donate and c.can_receive and a.route_id not in self.no_donate
                and c.route_id not in self.no_receive and reachable(self, a.route_id, c.route_id))


def band_cost(r: RouteInput, b: int, h: float) -> float:
    """Waiting + overcrowding cost of running headway h in band b."""
    wait = r.board_p50[b] * BAND_MIN * h / 2
    trips = BAND_MIN / h
    excess = max(0.0, r.flow_p90[b] * h - r.capacity) * trips
    return wait + OVERCROWD_W * excess


def route_cost(r: RouteInput, avail: int) -> tuple[float, list[int]]:
    """Best cost for a route given `avail` buses (used by greedy and for effects)."""
    total, hs = 0.0, []
    feas = [h for h in r.options() if r.buses_for(h) <= avail]
    if not feas:
        return math.inf, []
    for b in range(len(r.board_p50)):
        h = min(feas, key=lambda x: band_cost(r, b, x))
        hs.append(h)
        total += band_cost(r, b, h)
    return total, hs


def reachable(p: Problem, a: str | None, r: str | None) -> bool:
    km = p.deadhead_km.get((a, r))
    return km is not None and km / p.deadhead_speed_kmh * 60 <= MAX_DEADHEAD_MIN


def solve(p: Problem, time_limit_s: float = 5.0) -> Plan:
    t0 = time.perf_counter()
    m = cp_model.CpModel()
    R = {r.route_id: r for r in p.routes}
    ids = list(R)
    nb = len(p.routes[0].board_p50) if p.routes else 0
    moves_left = p.moves_left or {rid: MAX_CHANGES_PER_HOUR for rid in ids}

    x = {}
    for rid, r in R.items():
        opts = r.options()
        for b in range(nb):
            for h in opts:
                x[rid, b, h] = m.NewBoolVar(f"x_{rid}_{b}_{h}")
            m.AddExactlyOne(x[rid, b, h] for h in opts)

    mv, mv_on = {}, {}
    for a in ids:
        for c in ids:
            if a != c and p.may_move(R[a], R[c]):
                mv[a, c] = m.NewIntVar(0, min(MAX_BUSES_PER_ACTION, max(0, R[a].n_buses - 1)), f"m_{a}_{c}")
                mv_on[a, c] = m.NewBoolVar(f"mon_{a}_{c}")
                m.Add(mv[a, c] <= R[a].n_buses * mv_on[a, c])
                m.Add(mv[a, c] >= mv_on[a, c])
    add, add_on, rel, rel_on = {}, {}, {}, {}
    for c in ids:
        dep = R[c].depot_id
        cap = p.reserve.get(dep, 0)
        if cap > 0 and reachable(p, None, c) and R[c].can_receive and c not in p.no_receive:
            add[c] = m.NewIntVar(0, min(cap, MAX_BUSES_PER_ACTION), f"u_{c}")
            add_on[c] = m.NewBoolVar(f"uon_{c}")
            m.Add(add[c] <= cap * add_on[c])
            m.Add(add[c] >= add_on[c])
        rel_ok = R[c].can_release and c not in p.no_donate
        rel[c] = m.NewIntVar(0, min(MAX_BUSES_PER_ACTION, max(0, R[c].n_buses - 1)) if rel_ok else 0, f"z_{c}")
        rel_on[c] = m.NewBoolVar(f"zon_{c}")
        m.Add(rel[c] <= R[c].n_buses * rel_on[c])
        m.Add(rel[c] >= rel_on[c])
    for dep, cap in p.reserve.items():
        terms = [add[c] for c in add if R[c].depot_id == dep]
        if terms:
            m.Add(sum(terms) <= cap)

    avail = {}
    for c in ids:
        inflow = [mv[a, c] for a in ids if (a, c) in mv]
        outflow = [mv[c, d] for d in ids if (c, d) in mv]
        expr = R[c].n_buses + sum(inflow) - sum(outflow) - rel[c] + (add[c] if c in add else 0)
        avail[c] = m.NewIntVar(0, R[c].n_buses + sum(R[a].n_buses for a in ids) + 10, f"avail_{c}")
        m.Add(avail[c] == expr)
        # duty hours: only drivers with enough duty left can be moved or released
        if R[c].duty_ok is not None:
            m.Add(sum(outflow) + rel[c] <= R[c].duty_ok)
        # buses needed for the chosen headway must be available, every band
        for b in range(nb):
            m.Add(sum(R[c].buses_for(h) * x[c, b, h] for h in R[c].options()) <= avail[c])
        # at most N move actions touching a route per hour
        touching = ([mv_on[a, c] for a in ids if (a, c) in mv_on] + [mv_on[c, d] for d in ids if (c, d) in mv_on]
                    + [rel_on[c]] + ([add_on[c]] if c in add_on else []))
        m.Add(sum(touching) <= max(0, moves_left.get(c, MAX_CHANGES_PER_HOUR)))

    # headway changes: <= 2 per route per hour (two 30-min bands)
    changes = []
    for rid, r in R.items():
        opts = r.options()
        prev_opt = r.option_now()
        ch = []
        for b in range(nb):
            c = m.NewBoolVar(f"ch_{rid}_{b}")
            for h in opts:
                prev = x[rid, b - 1, h] if b > 0 else (1 if h == prev_opt else 0)
                m.Add(c >= x[rid, b, h] - prev)
            ch.append(c)
        for b in range(nb - 1):
            m.Add(ch[b] + ch[b + 1] <= MAX_CHANGES_PER_HOUR)
        changes.extend(ch)

    obj = []
    for (rid, b, h), var in x.items():
        obj.append(int(round(SCALE * band_cost(R[rid], b, h))) * var)
    for (a, c), var in mv.items():
        obj.append(int(round(SCALE * (MOVE_BUS_W + DEADHEAD_W * p.deadhead_km[a, c]))) * var)
        obj.append(int(SCALE * MOVE_W) * mv_on[a, c])
    for c, var in add.items():
        obj.append(int(round(SCALE * (ADD_W * nb + DEADHEAD_W * p.deadhead_km[None, c]))) * var)
        obj.append(int(SCALE * MOVE_W) * add_on[c])
    for c, var in rel.items():
        obj.append(int(round(SCALE * (DEADHEAD_W * p.deadhead_km.get((c, None), 5.0) - RELEASE_W * nb))) * var)
        obj.append(int(SCALE * MOVE_W) * rel_on[c])
    obj.extend(int(SCALE * CHANGE_W) * c for c in changes)
    m.Minimize(sum(obj))

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.max_time_in_seconds = time_limit_s
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        from .greedy import solve_greedy

        plan = solve_greedy(p)
        plan.status = f"cp_sat_{solver.StatusName(status).lower()}_fallback"
        plan.runtime_s = round(time.perf_counter() - t0, 3)
        return plan

    plan = Plan(solver="cp_sat", status=solver.StatusName(status).lower(),
                objective=solver.ObjectiveValue() / SCALE)
    for (a, c), var in mv.items():
        k = solver.Value(var)
        if k > 0:
            plan.actions.append(Action("move_bus", a, c, k, p.deadhead_km[a, c]))
    for c, var in add.items():
        k = solver.Value(var)
        if k > 0:
            plan.actions.append(Action("add_trip", None, c, k, p.deadhead_km[None, c]))
    for c, var in rel.items():
        k = solver.Value(var)
        if k > 0:
            plan.actions.append(Action("release_bus", c, None, k, p.deadhead_km.get((c, None), 5.0)))
    for rid, r in R.items():
        plan.headways[rid] = [float(next(h for h in r.options() if solver.Value(x[rid, b, h]))) for b in range(nb)]
        plan.fleet_after[rid] = solver.Value(avail[rid])
    plan.runtime_s = round(time.perf_counter() - t0, 3)
    return plan
