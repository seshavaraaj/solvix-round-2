"""Shared network-build helpers for gtfs_subset.py: config.json and the planned
timetable (gtfs/trips.parquet, gtfs/stop_times.parquet) from planned headways.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ARTEFACTS, DATA_PREP  # noqa: E402

from app.core.network import load_network  # noqa: E402
from app.core.timeutil import hhmm_to_s  # noqa: E402
from app.core.traveltime import TravelTime  # noqa: E402


def write_config(cluster: dict, demand: dict, scenarios: dict, holidays: list[str]) -> None:
    network_cfg = {k: cluster[k] for k in ("timezone", "capacity_rated", "capacity_crush", "layover_min",
                                            "deadhead_speed_kmh")}
    network_cfg["holidays"] = holidays
    cfg = {"network": network_cfg, "demand": demand, "scenarios": scenarios}
    (ARTEFACTS / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def read_holidays() -> list[str]:
    path = DATA_PREP / "holidays.csv"
    if not path.exists():
        return []
    return pl.read_csv(path)["date"].cast(pl.Utf8).to_list()


def build_timetable() -> None:
    """Planned trips and stop times 05:00–23:00 from planned headways."""
    net = load_network(ARTEFACTS)
    tt = TravelTime(net)
    trips, times = [], []
    for rid, r in net.routes.items():
        n_buses = math.ceil(tt.cycle_min(rid, 18 * 60) / r.planned_headway_min)
        for d in (0, 1):
            t = hhmm_to_s("05:00") + (d * r.planned_headway_min * 30)
            k = 0
            while t < hhmm_to_s("23:00"):
                trip_id = f"{rid}_{d}_{k:03d}"
                trips.append({"trip_id": trip_id, "route_id": rid, "direction_id": d,
                              "block_id": f"{rid}_blk{(k * 2 + d) % n_buses:02d}", "start_s": int(t)})
                seg = tt.seg_times_s(rid, d, t / 60)
                off = 0.0
                for i, sid in enumerate(r.stops(d)):
                    times.append({"trip_id": trip_id, "stop_seq": i, "stop_id": sid, "sched_s": int(t + off)})
                    if i < len(seg):
                        off += seg[i] + tt.dwell_min
                t += r.planned_headway_min * 60
                k += 1
    pl.DataFrame(trips).write_parquet(ARTEFACTS / "gtfs" / "trips.parquet")
    pl.DataFrame(times).write_parquet(ARTEFACTS / "gtfs" / "stop_times.parquet")
