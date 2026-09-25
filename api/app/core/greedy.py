"""Greedy fallback (solution2 §6.6): move one bus at a time from the route
where it costs least to the route where it helps most, while every constraint
holds. Used when CP-SAT finds no feasible answer inside its time limit."""
from __future__ import annotations

import math
import time

from .optimise import (ADD_W, DEADHEAD_W, MAX_BUSES_PER_ACTION, MAX_CHANGES_PER_HOUR, MOVE_BUS_W, MOVE_W,
                       RELEASE_W, Action, Plan, Problem, reachable, route_cost)

MAX_STEPS = 8


def solve_greedy(p: Problem) -> Plan:
    t0 = time.perf_counter()
    R = {r.route_id: r for r in p.routes}
    avail = {rid: r.n_buses for rid, r in R.items()}
    reserve = dict(p.reserve)
    moved_out = {rid: 0 for rid in R}
    actions: dict[tuple[str, str | None, str | None], int] = {}
    touches = {rid: 0 for rid in R}
    left = p.moves_left or {rid: MAX_CHANGES_PER_HOUR for rid in R}
    cost = {rid: route_cost(R[rid], avail[rid])[0] for rid in R}
    nb = len(p.routes[0].board_p50) if p.routes else 0

    def touch_ok(key: tuple, *rids: str | None) -> bool:
        if key in actions:
            return actions[key] < MAX_BUSES_PER_ACTION  # adding to an existing action is not a new change
        return all(r is None or touches[r] < left.get(r, MAX_CHANGES_PER_HOUR) for r in rids)

    for _ in range(MAX_STEPS):
        best = None
        for c in R:
            gain_in = cost[c] - route_cost(R[c], avail[c] + 1)[0]
            if not math.isfinite(gain_in):
                gain_in = 0.0
            # donors
            for a in R:
                if a == c or avail[a] <= 1 or not p.may_move(R[a], R[c]):
                    continue
                if not math.isfinite(cost[a]):
                    continue  # donor already below its service guarantee
                if R[a].duty_ok is not None and moved_out[a] >= R[a].duty_ok:
                    continue
                key = ("move_bus", a, c)
                if not touch_ok(key, a, c):
                    continue
                loss_out = route_cost(R[a], avail[a] - 1)[0] - cost[a]
                if not math.isfinite(loss_out):
                    continue  # donor would break its minimum frequency
                penalty = MOVE_BUS_W + DEADHEAD_W * p.deadhead_km[a, c] + (0 if key in actions else MOVE_W)
                delta = loss_out - gain_in + penalty
                if best is None or delta < best[0]:
                    best = (delta, key)
            # depot reserve
            dep = R[c].depot_id
            key = ("add_trip", None, c)
            if (reserve.get(dep, 0) > 0 and reachable(p, None, c) and R[c].can_receive
                    and c not in p.no_receive and touch_ok(key, c)):
                delta = (-gain_in + ADD_W * nb + DEADHEAD_W * p.deadhead_km[None, c]
                         + (0 if key in actions else MOVE_W))
                if best is None or delta < best[0]:
                    best = (delta, key)
            # release
            key = ("release_bus", c, None)
            if avail[c] > 1 and R[c].can_release and c not in p.no_donate and touch_ok(key, c):
                loss = route_cost(R[c], avail[c] - 1)[0] - cost[c]
                if math.isfinite(loss):
                    delta = (loss - RELEASE_W * nb + DEADHEAD_W * p.deadhead_km.get((c, None), 5.0)
                             + (0 if key in actions else MOVE_W))
                    if best is None or delta < best[0]:
                        best = (delta, key)
        if best is None or not math.isfinite(best[0]) or best[0] >= 0:
            break
        _, key = best
        kind, a, c = key
        if key not in actions:
            for r in (a, c):
                if r is not None:
                    touches[r] += 1
        actions[key] = actions.get(key, 0) + 1
        if a is not None:
            avail[a] -= 1
            moved_out[a] += 1
            cost[a] = route_cost(R[a], avail[a])[0]
        else:
            reserve[R[c].depot_id] -= 1
        if c is not None:
            avail[c] += 1
            cost[c] = route_cost(R[c], avail[c])[0]
        else:
            reserve[R[a].depot_id] = reserve.get(R[a].depot_id, 0) + 1

    plan = Plan(solver="greedy", status="greedy", objective=sum(cost.values()))
    for (kind, a, c), k in actions.items():
        plan.actions.append(Action(kind, a, c, k, p.deadhead_km.get((a, c), 5.0)))
    for rid in R:
        plan.headways[rid] = route_cost(R[rid], avail[rid])[1]
        plan.fleet_after[rid] = avail[rid]
    plan.runtime_s = round(time.perf_counter() - t0, 3)
    return plan
