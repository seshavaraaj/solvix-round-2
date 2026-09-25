"""Filter the Delhi OTD static GTFS to the route cluster (plan B1.2).

Replaces build_network.py's stand-in network once the real zip is downloaded
from https://otd.delhi.gov.in (free registration). Writes the same Parquet
schema to data/artefacts/gtfs/, so nothing downstream changes.

Per route: the most frequent shape and stop pattern of direction 0 becomes the
route geometry; direction 1 is its reverse (as in build_network.py). Depots,
minimum headways and busy factors are not in GTFS and come from cluster.yaml.

Run: python offline/data_prep/gtfs_subset.py data/raw/delhi_gtfs.zip [--routes 534 423 ...]
Then re-run: weather.py, synthetic_etm.py, derive.py, build_replay.py, models/train.py
"""
from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ARTEFACTS, DATA_PREP, load_yaml  # noqa: E402
from data_prep.build_network import build_timetable, read_holidays, write_config  # noqa: E402
from data_prep.clean_rt import project  # noqa: E402

from app.core.network import Route, haversine_km  # noqa: E402


def read(z: zipfile.ZipFile, name: str) -> pl.DataFrame:
    return pl.read_csv(io.BytesIO(z.read(name)), infer_schema_length=0)  # all columns as strings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("zip")
    ap.add_argument("--routes", nargs="*", help="GTFS route_short_name or route_id values")
    args = ap.parse_args()
    cluster = load_yaml(DATA_PREP / "cluster.yaml")
    wanted = args.routes or [r["id"] for r in cluster["routes"]]
    meta = {r["id"]: r for r in cluster["routes"]}

    z = zipfile.ZipFile(args.zip)
    routes = read(z, "routes.txt").filter(pl.col("route_short_name").is_in(wanted) | pl.col("route_id").is_in(wanted))
    trips = read(z, "trips.txt").filter(pl.col("route_id").is_in(routes["route_id"].to_list()))
    stop_times = read(z, "stop_times.txt").filter(pl.col("trip_id").is_in(trips["trip_id"].to_list()))
    stops = read(z, "stops.txt")
    shapes = read(z, "shapes.txt") if "shapes.txt" in z.namelist() else None

    gtfs = ARTEFACTS / "gtfs"
    gtfs.mkdir(parents=True, exist_ok=True)
    route_rows, rs_rows, shape_rows, used_stops = [], [], [], set()
    for r in routes.iter_rows(named=True):
        rid = r["route_short_name"] or r["route_id"]
        m = meta.get(rid, {})
        t = trips.filter((pl.col("route_id") == r["route_id"]) & (pl.col("direction_id").fill_null("0") == "0"))
        if t.height == 0:
            print(f"skip {rid}: no direction-0 trips")
            continue
        # most frequent stop pattern
        st = (stop_times.filter(pl.col("trip_id").is_in(t["trip_id"].to_list()))
              .with_columns(pl.col("stop_sequence").cast(pl.Int32)).sort(["trip_id", "stop_sequence"]))
        pattern = (st.group_by("trip_id", maintain_order=True).agg(pl.col("stop_id"))
                   .with_columns(pl.col("stop_id").list.join("|").alias("p"))["p"].value_counts(sort=True))
        stop_ids = pattern["p"][0].split("|")
        used_stops.update(stop_ids)
        s = stops.filter(pl.col("stop_id").is_in(stop_ids))
        pos = {x["stop_id"]: (float(x["stop_lat"]), float(x["stop_lon"])) for x in s.iter_rows(named=True)}
        if shapes is not None and "shape_id" in t.columns and t["shape_id"].drop_nulls().len():
            shape_id = t["shape_id"].value_counts(sort=True)["shape_id"][0]
            pts = (shapes.filter(pl.col("shape_id") == shape_id)
                   .with_columns(pl.col("shape_pt_sequence").cast(pl.Int32)).sort("shape_pt_sequence"))
            coords = np.array([[float(a), float(b)] for a, b in zip(pts["shape_pt_lat"], pts["shape_pt_lon"])])
        else:
            coords = np.array([pos[x] for x in stop_ids])
        km = np.concatenate([[0.0], np.cumsum([haversine_km(*coords[i], *coords[i + 1])
                                                for i in range(len(coords) - 1)])])
        tmp = Route(rid, "", "", "", 0, 0, 0, stop_ids, coords, km, np.zeros(len(stop_ids)))
        stop_km = sorted(project(tmp, *pos[x])[0] for x in stop_ids)
        total = km[-1]
        for d, seq, kms in ((0, stop_ids, stop_km), (1, stop_ids[::-1], [total - k for k in stop_km[::-1]])):
            for i, (sid, k) in enumerate(zip(seq, kms)):
                rs_rows.append({"route_id": rid, "direction_id": d, "stop_seq": i, "stop_id": sid,
                                "dist_km": round(float(k), 4)})
        for i, ((la, lo), k) in enumerate(zip(coords, km)):
            shape_rows.append({"shape_id": rid, "pt_seq": i, "lat": la, "lon": lo, "dist_km": round(float(k), 4)})
        route_rows.append({
            "route_id": rid, "route_short_name": rid, "route_long_name": r.get("route_long_name") or m.get("name", rid),
            "route_color": "#" + r["route_color"] if r.get("route_color") else m.get("color", "#555555"),
            "depot_id": m.get("depot_id", cluster["depots"][0]["id"]),
            "planned_headway_min": float(m.get("planned_headway_min", 15)),
            "min_headway_min": float(m.get("min_headway_min", 20)), "busy_factor": float(m.get("busy_factor", 1.0)),
        })
    types = {s["id"]: s["type"] for s in cluster["stops"]}
    pl.DataFrame([{"stop_id": x["stop_id"], "stop_name": x["stop_name"], "stop_lat": float(x["stop_lat"]),
                   "stop_lon": float(x["stop_lon"]), "stop_type": types.get(x["stop_id"], "minor")}
                  for x in stops.filter(pl.col("stop_id").is_in(list(used_stops))).iter_rows(named=True)]
                 ).write_parquet(gtfs / "stops.parquet")
    pl.DataFrame(route_rows).write_parquet(gtfs / "routes.parquet")
    pl.DataFrame(rs_rows).write_parquet(gtfs / "route_stops.parquet")
    pl.DataFrame(shape_rows).write_parquet(gtfs / "shapes.parquet")
    pl.DataFrame([{"depot_id": d["id"], **{k: d[k] for k in ("name", "lat", "lon", "fleet_size", "reserve",
                                                             "out_of_service")}} for d in cluster["depots"]]
                 ).write_parquet(gtfs / "depots.parquet")
    write_config(cluster, load_yaml(DATA_PREP / "demand_params.yaml"), load_yaml(DATA_PREP / "scenarios.yaml"),
                 read_holidays())
    build_timetable()
    print(f"wrote {len(route_rows)} routes, {len(used_stops)} stops from {args.zip}")
    print("Stop types default to 'minor' unless listed in cluster.yaml; review them before synthetic_etm.py.")


if __name__ == "__main__":
    main()
