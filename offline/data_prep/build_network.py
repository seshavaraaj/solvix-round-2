"""Build the route-cluster artefacts from cluster.yaml (stand-in for the Delhi
OTD static GTFS until the real zip is downloaded; see gtfs_subset.py).

Writes data/artefacts/gtfs/{routes,stops,route_stops,shapes,depots,trips,
stop_times}.parquet and data/artefacts/config.json.

Run: python offline/data_prep/build_network.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ARTEFACTS, DATA_PREP, load_yaml  # noqa: E402

from app.core.network import haversine_km, load_network  # noqa: E402
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


def build_static(cluster: dict) -> None:
    gtfs = ARTEFACTS / "gtfs"
    gtfs.mkdir(parents=True, exist_ok=True)
    stops = {s["id"]: s for s in cluster["stops"]}
    pl.DataFrame([
        {"stop_id": s["id"], "stop_name": s["name"], "stop_lat": s["lat"], "stop_lon": s["lon"], "stop_type": s["type"]}
        for s in cluster["stops"]
    ]).write_parquet(gtfs / "stops.parquet")
    pl.DataFrame([
        {"route_id": r["id"], "route_short_name": r["id"], "route_long_name": r["name"], "route_color": r["color"],
         "depot_id": r["depot_id"], "planned_headway_min": float(r["planned_headway_min"]),
         "min_headway_min": float(r["min_headway_min"]), "busy_factor": float(r["busy_factor"])}
        for r in cluster["routes"]
    ]).write_parquet(gtfs / "routes.parquet")
    pl.DataFrame([{"depot_id": d["id"], **{k: d[k] for k in ("name", "lat", "lon", "fleet_size", "reserve",
                                                             "out_of_service")}}
                  for d in cluster["depots"]]).write_parquet(gtfs / "depots.parquet")

    rs_rows, shape_rows = [], []
    for r in cluster["routes"]:
        ids = r["stops"]
        km = [0.0]
        for a, b in zip(ids, ids[1:]):
            km.append(km[-1] + haversine_km(stops[a]["lat"], stops[a]["lon"], stops[b]["lat"], stops[b]["lon"]))
        total = km[-1]
        for d, seq in ((0, ids), (1, ids[::-1])):
            kms = km if d == 0 else [total - k for k in km[::-1]]
            for i, (sid, k) in enumerate(zip(seq, kms)):
                rs_rows.append({"route_id": r["id"], "direction_id": d, "stop_seq": i, "stop_id": sid,
                                "dist_km": round(k, 4)})
        # shape = straight lines between stops (real GTFS shapes replace this)
        for i, (sid, k) in enumerate(zip(ids, km)):
            shape_rows.append({"shape_id": r["id"], "pt_seq": i, "lat": stops[sid]["lat"], "lon": stops[sid]["lon"],
                               "dist_km": round(k, 4)})
    pl.DataFrame(rs_rows).write_parquet(gtfs / "route_stops.parquet")
    pl.DataFrame(shape_rows).write_parquet(gtfs / "shapes.parquet")


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


def main() -> None:
    ARTEFACTS.mkdir(parents=True, exist_ok=True)
    cluster = load_yaml(DATA_PREP / "cluster.yaml")
    demand = load_yaml(DATA_PREP / "demand_params.yaml")
    scenarios = load_yaml(DATA_PREP / "scenarios.yaml")
    write_config(cluster, demand, scenarios, read_holidays())
    build_static(cluster)
    build_timetable()
    net = load_network(ARTEFACTS)
    tt = TravelTime(net)
    for rid, r in net.routes.items():
        c = tt.cycle_min(rid, 18 * 60)
        print(f"route {rid}: {r.length_km:5.1f} km, cycle {c:5.1f} min, "
              f"planned buses {math.ceil(c / r.planned_headway_min)}")


if __name__ == "__main__":
    main()
