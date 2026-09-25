"""Clean recorded GTFS-RT positions (plan B1.4, solution2 §6.1 step 3).

- map-match each position to its route shape (nearest point on the polyline);
- drop points more than 50 m from the route;
- infer direction from movement along the shape;
- mark a bus "dark" after 2 minutes without a report.

Input:  data/raw/rt/<date>.parquet (from record_rt.py)
Output: data/raw/rt_clean/<date>.parquet
        bus_id, route_id, direction, t_s, dist_km, lat, lon, dark_before

Run: python offline/data_prep/clean_rt.py 2026-09-23
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ARTEFACTS, RAW  # noqa: E402

from app.core.network import Route, load_network  # noqa: E402
from app.core.timeutil import IST  # noqa: E402

MAX_OFF_ROUTE_M = 50.0
DARK_AFTER_S = 120


def project(route: Route, lat: float, lon: float) -> tuple[float, float]:
    """(distance along direction-0 shape in km, distance off route in m)."""
    k = 111.32 * np.cos(np.radians(lat))           # km per degree of longitude
    pts = np.column_stack([route.shape[:, 1] * k, route.shape[:, 0] * 110.57])
    p = np.array([lon * k, lat * 110.57])
    a, b = pts[:-1], pts[1:]
    ab = b - a
    t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1)
    proj = a + ab * t[:, None]
    d = np.hypot(*(proj - p).T)
    i = int(np.argmin(d))
    along = route.shape_km[i] + t[i] * (route.shape_km[i + 1] - route.shape_km[i])
    return float(along), float(d[i] * 1000)


def clean_day(day: str) -> pl.DataFrame:
    net = load_network(ARTEFACTS)
    raw = pl.read_parquet(RAW / "rt" / f"{day}.parquet").sort(["vehicle_id", "ts"])
    out = []
    for (vid,), g in raw.group_by(["vehicle_id"], maintain_order=True):
        prev_t, prev_km = None, None
        direction = 0
        for r in g.iter_rows(named=True):
            route = net.routes.get(r["route_id"])
            if route is None:
                continue
            km0, off = project(route, r["lat"], r["lon"])
            if off > MAX_OFF_ROUTE_M:
                continue
            dt = datetime.fromtimestamp(r["ts"], IST)
            t_s = dt.hour * 3600 + dt.minute * 60 + dt.second
            if prev_km is not None and abs(km0 - prev_km) > 0.02:
                direction = 0 if km0 > prev_km else 1
            dark = prev_t is not None and t_s - prev_t > DARK_AFTER_S
            out.append({"bus_id": f"bus_{vid}", "route_id": route.id, "direction": direction, "t_s": t_s,
                        "dist_km": round(km0 if direction == 0 else route.length_km - km0, 4),
                        "lat": r["lat"], "lon": r["lon"], "dark_before": dark})
            prev_t, prev_km = t_s, km0
    return pl.DataFrame(out)


def main() -> None:
    day = sys.argv[1]
    df = clean_day(day)
    out = RAW / "rt_clean"
    out.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out / f"{day}.parquet")
    print(f"{day}: {df.height} clean positions, {df['bus_id'].n_unique()} buses")


if __name__ == "__main__":
    main()
