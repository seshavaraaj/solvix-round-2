"""Record a GTFS-realtime VehiclePositions feed (plan B1.3).

Polls every 30 s and appends one row per vehicle position for the cluster
routes to data/raw/rt/<date>.parquet (git-ignored). Record at least 3
weekdays and 1 weekend day, then run clean_rt.py and derive.py.

The feed URL comes from GTFS_RT_URL and the API key from GTFS_RT_KEY in a
local .env file. Never commit the key. Chennai MTC has no public GTFS-RT feed
yet, so there is no default URL.

Run: python offline/data_prep/record_rt.py [--hours 4]
Needs: pip install gtfs-realtime-bindings (offline/requirements.txt)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ARTEFACTS, RAW  # noqa: E402

from app.config import settings  # noqa: E402  (loads .env)
from app.core.timeutil import IST  # noqa: E402

POLL_S = 30
FLUSH_EVERY = 10


def fetch_positions(url: str, key: str) -> list[dict]:
    from google.transit import gtfs_realtime_pb2

    sep = "&" if "?" in url else "?"
    with urllib.request.urlopen(f"{url}{sep}key={key}", timeout=20) as resp:
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(resp.read())
    rows = []
    for ent in feed.entity:
        if not ent.HasField("vehicle"):
            continue
        v = ent.vehicle
        rows.append({
            "vehicle_id": v.vehicle.id or ent.id,
            "route_id": v.trip.route_id,
            "trip_id": v.trip.trip_id,
            "lat": v.position.latitude,
            "lon": v.position.longitude,
            "bearing": v.position.bearing,
            "speed": v.position.speed,
            "ts": int(v.timestamp),
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=4.0)
    args = ap.parse_args()
    if not settings.gtfs_rt_url:
        sys.exit("Set GTFS_RT_URL in .env (no public Chennai MTC feed exists yet)")
    key = settings.gtfs_rt_key or os.getenv("GTFS_RT_KEY")
    if not key:
        sys.exit("Set GTFS_RT_KEY in .env (key for the feed at GTFS_RT_URL)")
    routes = set(pl.read_parquet(ARTEFACTS / "gtfs" / "routes.parquet")["route_id"].to_list())
    out_dir = RAW / "rt"
    out_dir.mkdir(parents=True, exist_ok=True)
    buffer: list[dict] = []
    end = time.time() + args.hours * 3600
    polls = 0
    while time.time() < end:
        started = time.time()
        try:
            rows = [r for r in fetch_positions(settings.gtfs_rt_url, key) if r["route_id"] in routes]
            buffer.extend(rows)
            print(f"{datetime.now(IST):%H:%M:%S} {len(rows)} positions")
        except Exception as exc:
            print(f"poll failed: {exc}")
        polls += 1
        if polls % FLUSH_EVERY == 0 and buffer:
            flush(buffer, out_dir)
            buffer = []
        time.sleep(max(0.0, POLL_S - (time.time() - started)))
    if buffer:
        flush(buffer, out_dir)


def flush(rows: list[dict], out_dir: Path) -> None:
    df = pl.DataFrame(rows)
    day = datetime.now(IST).date().isoformat()
    path = out_dir / f"{day}.parquet"
    if path.exists():
        df = pl.concat([pl.read_parquet(path), df], how="vertical_relaxed")
    df.unique(subset=["vehicle_id", "ts"]).write_parquet(path)


if __name__ == "__main__":
    main()
