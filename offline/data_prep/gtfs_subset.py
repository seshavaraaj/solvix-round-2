"""Filter a static GTFS feed to the route cluster in cluster.yaml (plan B1.2).

Default feed: the community Chennai MTC GTFS by UngalSoththu (ODbL; attribution
"UngalSoththu, ChennaiGTFS"), downloaded to data/raw/ (git-ignored) if missing.
MTC publishes no official open GTFS; this feed was collected from the MTC app.

Each cluster route names one GTFS `gtfs_route_id` (in this feed every
direction is its own route_id). Its most frequent stop pattern becomes
direction 0; direction 1 is its reverse. Depots, headways, busy factors and
stop types are not in GTFS and come from cluster.yaml. Writes
data/artefacts/gtfs/*.parquet and data/artefacts/config.json.

Run: python offline/data_prep/gtfs_subset.py [path/to/gtfs.zip]
Then re-run: weather.py, synthetic_etm.py, derive.py, build_replay.py, models/train.py
(offline/run_all.py does all of this.)
"""
from __future__ import annotations

import argparse
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ARTEFACTS, DATA_PREP, RAW, load_yaml  # noqa: E402
from data_prep.build_network import build_timetable, read_holidays, write_config  # noqa: E402

from app.core.network import haversine_km  # noqa: E402

DEFAULT_ZIP = RAW / "chennai_gtfs.zip"


def read(z: zipfile.ZipFile, name: str) -> pl.DataFrame:
    # all columns as strings; the unified Chennai feed appends metro rows with extra columns
    return pl.read_csv(io.BytesIO(z.read(name)), infer_schema_length=0, truncate_ragged_lines=True)


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:
        dest.write_bytes(resp.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("zip", nargs="?", default=str(DEFAULT_ZIP))
    args = ap.parse_args()
    cluster = load_yaml(DATA_PREP / "cluster.yaml")
    zip_path = Path(args.zip)
    if not zip_path.exists():
        download(cluster["gtfs"]["url"], zip_path)

    z = zipfile.ZipFile(zip_path)
    trips = read(z, "trips.txt")
    stop_times = read(z, "stop_times.txt")
    stops = read(z, "stops.txt")
    pos = {x["stop_id"]: (float(x["stop_lat"]), float(x["stop_lon"]), x["stop_name"])
           for x in stops.iter_rows(named=True) if x["stop_lat"] and x["stop_lon"]}

    gtfs = ARTEFACTS / "gtfs"
    gtfs.mkdir(parents=True, exist_ok=True)
    route_rows, rs_rows, shape_rows, used_stops = [], [], [], set()
    for m in cluster["routes"]:
        rid = m["id"]
        t = trips.filter(pl.col("route_id") == str(m["gtfs_route_id"]))
        if t.height == 0:
            sys.exit(f"route {rid}: gtfs_route_id {m['gtfs_route_id']} has no trips in {zip_path}")
        # most frequent stop pattern
        st = (stop_times.filter(pl.col("trip_id").is_in(t["trip_id"].to_list()))
              .with_columns(pl.col("stop_sequence").cast(pl.Int32)).sort(["trip_id", "stop_sequence"]))
        pattern = (st.group_by("trip_id", maintain_order=True).agg(pl.col("stop_id"))
                   .with_columns(pl.col("stop_id").list.join("|").alias("p"))["p"].value_counts(sort=True))
        stop_ids = [x for x in pattern["p"][0].split("|") if x in pos]
        used_stops.update(stop_ids)
        # no trip shapes in this feed: the shape is the stop sequence
        km = [0.0]
        for a, b in zip(stop_ids, stop_ids[1:]):
            km.append(km[-1] + haversine_km(pos[a][0], pos[a][1], pos[b][0], pos[b][1]))
        total = km[-1]
        for d, seq, kms in ((0, stop_ids, km), (1, stop_ids[::-1], [total - k for k in km[::-1]])):
            for i, (sid, k) in enumerate(zip(seq, kms)):
                rs_rows.append({"route_id": rid, "direction_id": d, "stop_seq": i, "stop_id": sid,
                                "dist_km": round(float(k), 4)})
        for i, (sid, k) in enumerate(zip(stop_ids, km)):
            shape_rows.append({"shape_id": rid, "pt_seq": i, "lat": pos[sid][0], "lon": pos[sid][1],
                               "dist_km": round(float(k), 4)})
        route_rows.append({
            "route_id": rid, "route_short_name": rid, "route_long_name": m["name"], "route_color": m["color"],
            "depot_id": m["depot_id"], "planned_headway_min": float(m["planned_headway_min"]),
            "min_headway_min": float(m["min_headway_min"]), "busy_factor": float(m["busy_factor"]),
        })
        print(f"route {rid}: {len(stop_ids)} stops, {total:.1f} km, {t.height} GTFS trips/day")

    types = {str(k): v for k, v in cluster["stop_types"].items()}
    default_type = cluster.get("default_stop_type", "minor")
    pl.DataFrame([{"stop_id": sid, "stop_name": pos[sid][2].strip(), "stop_lat": pos[sid][0],
                   "stop_lon": pos[sid][1], "stop_type": types.get(sid, default_type)}
                  for sid in sorted(used_stops)]).write_parquet(gtfs / "stops.parquet")
    pl.DataFrame(route_rows).write_parquet(gtfs / "routes.parquet")
    pl.DataFrame(rs_rows).write_parquet(gtfs / "route_stops.parquet")
    pl.DataFrame(shape_rows).write_parquet(gtfs / "shapes.parquet")
    pl.DataFrame([{"depot_id": d["id"], **{k: d[k] for k in ("name", "lat", "lon", "fleet_size", "reserve",
                                                             "out_of_service")}} for d in cluster["depots"]]
                 ).write_parquet(gtfs / "depots.parquet")
    write_config(cluster, load_yaml(DATA_PREP / "demand_params.yaml"), load_yaml(DATA_PREP / "scenarios.yaml"),
                 read_holidays())
    build_timetable()
    print(f"wrote {len(route_rows)} routes, {len(used_stops)} stops from {zip_path}")


if __name__ == "__main__":
    main()
