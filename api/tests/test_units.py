"""Features, templates, crowding blend, load estimation, simulator."""
import time

import numpy as np

from app.core.crowding import CAP, CrowdingStore, Report, blend
from app.core.explain import explain
from app.core.features import DEMAND_FEATURES, BaseDemand, demand_matrix, stop_groups
from app.core.loads import ipf_trip, onboard_from_od, segment_flow
from app.core.timeutil import hhmm_to_s, parse_iso, to_iso
from app.sim.model import Move, SimConfig, Simulation


def test_stop_groups_cover_three_parts():
    g = stop_groups(9)
    assert list(g) == [0, 0, 0, 1, 1, 1, 2, 2, 2]
    assert set(stop_groups(5)) == {0, 1, 2}


def test_demand_matrix_column_order():
    cols = {f: np.array([i]) for i, f in enumerate(DEMAND_FEATURES)}
    assert demand_matrix(cols).tolist() == [list(range(len(DEMAND_FEATURES)))]


def test_base_demand_peaks_in_evening(core):
    net, dm, _ = core
    base = BaseDemand(net, dm)
    assert base.get("534", 1, 0, 18 * 4) > base.get("534", 1, 0, 3 * 4) > 0


def test_time_roundtrip():
    iso = to_iso("2026-09-25", hhmm_to_s("17:30"))
    assert iso == "2026-09-25T17:30:00+05:30"
    assert parse_iso(iso) == ("2026-09-25", 63000)


def test_ipf_rows_match_boardings_and_loads_non_negative(core):
    net, dm, _ = core
    b = np.array([10, 5, 8, 3, 2, 0, 1, 4, 0], dtype=float)
    _, alight = dm._weights("534", 0, 18 * 60)
    od = ipf_trip(b, dm.dest_probs("534", 0, 18 * 60), alight)
    assert np.allclose(od.sum(axis=1), b)
    load = onboard_from_od(od)
    assert (load >= -1e-9).all() and abs(load[-1]) < 1e-9
    flow = segment_flow(np.ones(9), dm.dest_probs("534", 0, 18 * 60))
    assert len(flow) == 8 and flow.max() > 0


def test_crowding_blend_capped_at_30_percent():
    now = time.time()
    many = [Report("d", "b", "534", "crowded", now) for _ in range(50)]
    assert blend(0.5, many, now) <= 0.5 * (1 + CAP) + 1e-9
    empty = [Report("d", "b", "534", "empty", now) for _ in range(50)]
    assert blend(1.0, empty, now) >= 1.0 * (1 - CAP) - 1e-9
    assert blend(0.8, [], now) == 0.8


def test_crowding_recency_decay():
    now = time.time()
    fresh = blend(0.6, [Report("d", "b", "r", "crowded", now)], now)
    old = blend(0.6, [Report("d", "b", "r", "crowded", now - 3600)], now)
    assert fresh > old > 0.6


def test_crowding_rate_limit():
    s = CrowdingStore()
    now = time.time()
    s.add(Report("dev", "bus1", "534", "ok", now))
    assert not s.allowed("dev", "bus1", now + 60)
    assert s.allowed("dev", "bus2", now + 60)
    assert s.allowed("dev", "bus1", now + 301)


def test_template_numbers_come_from_record():
    rec = {
        "action": "move_bus", "from_route_id": "423", "to_route_id": "534", "bus_count": 2,
        "window_start": "2026-09-25T17:30:00+05:30", "window_end": "2026-09-25T19:00:00+05:30",
        "expected_effect": {
            "to_route": {"wait_min_before": 11.0, "wait_min_after": 7.0, "peak_load_before": 1.25,
                         "peak_load_after": 0.92},
            "from_route": {"wait_min_before": 7.5, "wait_min_after": 9.0, "peak_load_before": 0.28,
                           "peak_load_after": 0.41}},
        "deadhead_km": 6.0, "confidence": "high",
    }
    text = explain(rec, {"to_stop": "Nehru Place", "depot_name": "Okhla Depot", "from_min_headway": 15})
    assert text.startswith("Move 2 buses from Route 423 to Route 534, 17:30–19:00.")
    for piece in ("125%", "Nehru Place", "28%", "from 11 to 7 minutes", "15-minute minimum", "6 km",
                  "Confidence: high"):
        assert piece in text


def test_simulator_move_reduces_overload(core):
    net, dm, tt = core
    sc = net.scenarios["scenarios"]["event_surge"]
    base = dict(start_s=hhmm_to_s("17:00"), end_s=hhmm_to_s("19:00"), events=dm.events_for(sc),
                strategy="transitpulse", warmup_s=1800)
    over_wo, over_w = 0, 0
    t0 = time.perf_counter()
    for seed in range(3):
        over_wo += Simulation(net, dm, tt, SimConfig(**base, seed=seed)).run()["overload_min"]
        mv = Move(hhmm_to_s("17:00"), "423", "534", 2, 2.9)
        over_w += Simulation(net, dm, tt, SimConfig(**base, seed=seed, moves=[mv])).run()["overload_min"]
    assert over_w < over_wo
    assert time.perf_counter() - t0 < 20
