"""Optimiser constraints (min frequency never violated), greedy fallback, and
the expected decision on the demo scenarios."""
import math
import random

import pytest

from app.core.greedy import solve_greedy
from app.core.optimise import MAX_BUSES_PER_ACTION, Problem, RouteInput, solve
from app.core.planning import build_problem, route_inputs
from app.core.timeutil import hhmm_to_s
from app.sim.model import planned_fleet


def _route(rid, n, cycle, min_h, board, flow, depot="d1"):
    return RouteInput(route_id=rid, depot_id=depot, n_buses=n, cycle_min=cycle, min_headway_min=min_h,
                      board_p50=[board] * 3, flow_p50=[flow] * 3, flow_p90=[flow * 1.25] * 3, capacity=60)


def _problem(routes, reserve=2):
    ids = [r.route_id for r in routes]
    dh = {(a, c): 3.0 for a in ids for c in ids if a != c}
    dh.update({(None, a): 4.0 for a in ids})
    dh.update({(a, None): 4.0 for a in ids})
    return Problem(routes=routes, reserve={"d1": reserve}, deadhead_km=dh)


def _check_min_frequency(problem, plan):
    for r in problem.routes:
        n_after = plan.fleet_after[r.route_id]
        if n_after < r.n_buses:  # only routes that lost buses must still meet the guarantee
            assert r.cycle_min / n_after <= r.min_headway_min + 1e-6, (r.route_id, n_after)
        for h in plan.headways[r.route_id]:
            assert r.buses_for(h) <= n_after


def test_crowded_route_receives_from_quiet_route():
    busy = _route("3", 14, 156, 15, board=18, flow=7.0)
    quiet = _route("9M", 8, 115, 20, board=3, flow=1.0)
    plan = solve(_problem([busy, quiet], reserve=0))
    assert plan.solver == "cp_sat"
    moves = [a for a in plan.actions if a.action == "move_bus"]
    assert moves and moves[0].from_route_id == "9M" and moves[0].to_route_id == "3"
    assert all(a.bus_count <= MAX_BUSES_PER_ACTION for a in plan.actions)
    _check_min_frequency(_problem([busy, quiet]), plan)


def test_no_action_when_nothing_is_crowded():
    a = _route("a", 10, 120, 15, board=6, flow=2.5)
    b = _route("b", 8, 100, 20, board=4, flow=2.0)
    assert solve(_problem([a, b])).actions == []


@pytest.mark.parametrize("seed", range(25))
def test_min_frequency_never_violated_random(seed):
    rng = random.Random(seed)
    routes = [_route(f"r{i}", rng.randint(3, 15), rng.uniform(60, 170), rng.choice([15, 20]),
                     board=rng.uniform(1, 20), flow=rng.uniform(0.5, 9)) for i in range(5)]
    p = _problem(routes, reserve=rng.randint(0, 3))
    for plan in (solve(p), solve_greedy(p)):
        _check_min_frequency(p, plan)


def test_greedy_matches_direction_of_cp_sat():
    busy = _route("3", 14, 156, 15, board=18, flow=7.0)
    quiet = _route("9M", 8, 115, 20, board=3, flow=1.0)
    g = solve_greedy(_problem([busy, quiet], reserve=0))
    assert g.solver == "greedy"
    assert [(a.from_route_id, a.to_route_id) for a in g.actions] == [("9M", "3")]


def test_reversal_is_blocked():
    busy = _route("3", 14, 156, 15, board=18, flow=7.0)
    quiet = _route("9M", 8, 115, 20, board=3, flow=1.0)
    p = _problem([busy, quiet], reserve=0)
    p.no_donate, p.no_receive = {"9M"}, set()
    assert not [a for a in solve(p).actions if a.from_route_id == "9M"]


def test_event_surge_scenario_moves_bus_to_route_3(core):
    net, dm, tt = core
    sc = net.scenarios["scenarios"]["event_surge"]
    ev = dm.events_for(sc)
    f50 = lambda r, d, m: dm.board_rate(r, d, m, "weekday", 0.0, ev)  # noqa: E731
    f90 = lambda r, d, m: 1.25 * f50(r, d, m)  # noqa: E731
    inputs = route_inputs(net, dm, tt, hhmm_to_s("17:15"), planned_fleet(net, tt), f50, f90)
    plan = solve(build_problem(net, inputs, {"depot_adyar": 0, "depot_tnagar": 0}))
    assert any(a.action == "move_bus" and a.to_route_id == "3" for a in plan.actions)
    assert math.isfinite(plan.objective)
