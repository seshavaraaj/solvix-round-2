"""Route network loaded from data/artefacts/gtfs/*.parquet + config.json.

Direction 0 runs in the listed stop order, direction 1 in reverse. Distances
along a route are kilometres from the first stop of that direction.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import polars as pl

EARTH_R_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


@dataclass
class Stop:
    id: str
    name: str
    lat: float
    lon: float
    type: str = "minor"


@dataclass
class Depot:
    id: str
    name: str
    lat: float
    lon: float
    fleet_size: int
    reserve: int
    out_of_service: int


@dataclass
class Route:
    id: str
    name: str
    depot_id: str
    color: str
    planned_headway_min: float
    min_headway_min: float
    busy_factor: float
    stop_ids: list[str]            # direction 0 order
    shape: np.ndarray               # (n, 2) lat, lon along direction 0
    shape_km: np.ndarray            # cumulative km along shape, direction 0
    stop_km0: np.ndarray            # km of each stop along direction 0
    length_km: float = field(init=False)

    def __post_init__(self) -> None:
        self.length_km = float(self.shape_km[-1])

    def stops(self, direction: int) -> list[str]:
        return self.stop_ids if direction == 0 else self.stop_ids[::-1]

    def stop_km(self, direction: int) -> np.ndarray:
        return self.stop_km0 if direction == 0 else (self.length_km - self.stop_km0[::-1])

    def seg_km(self, direction: int) -> np.ndarray:
        return np.diff(self.stop_km(direction))

    def terminal(self, direction: int) -> str:
        """First stop of a trip in this direction."""
        return self.stops(direction)[0]

    def point_at(self, direction: int, km: float) -> tuple[float, float, float]:
        """lat, lon, bearing at `km` from the start of `direction`."""
        km0 = km if direction == 0 else self.length_km - km
        km0 = min(max(km0, 0.0), self.length_km)
        i = int(np.searchsorted(self.shape_km, km0, side="right") - 1)
        i = min(max(i, 0), len(self.shape_km) - 2)
        seg = self.shape_km[i + 1] - self.shape_km[i]
        f = 0.0 if seg <= 0 else (km0 - self.shape_km[i]) / seg
        lat = self.shape[i, 0] + f * (self.shape[i + 1, 0] - self.shape[i, 0])
        lon = self.shape[i, 1] + f * (self.shape[i + 1, 1] - self.shape[i, 1])
        a, b = (self.shape[i], self.shape[i + 1]) if direction == 0 else (self.shape[i + 1], self.shape[i])
        return float(lat), float(lon), round(bearing_deg(a[0], a[1], b[0], b[1]))

    def geojson(self) -> dict:
        return {"type": "LineString", "coordinates": [[round(lon, 6), round(lat, 6)] for lat, lon in self.shape]}


@dataclass
class Network:
    stops: dict[str, Stop]
    routes: dict[str, Route]
    depots: dict[str, Depot]
    config: dict
    demand_params: dict
    scenarios: dict

    @property
    def capacity(self) -> int:
        return int(self.config["capacity_rated"])

    @property
    def capacity_crush(self) -> int:
        return int(self.config["capacity_crush"])

    @property
    def layover_min(self) -> float:
        return float(self.config["layover_min"])

    def deadhead_km(self, from_stop: str, to_stop: str) -> float:
        a, b = self.stops[from_stop], self.stops[to_stop]
        return 1.3 * haversine_km(a.lat, a.lon, b.lat, b.lon)  # 1.3 = road detour factor

    def deadhead_min(self, from_stop: str, to_stop: str) -> float:
        return self.deadhead_km(from_stop, to_stop) / float(self.config["deadhead_speed_kmh"]) * 60.0

    def route_deadhead_km(self, from_route: str | None, to_route: str | None) -> float:
        """Shortest terminal-to-terminal deadhead between two routes (None = depot)."""
        def ends(route_id: str | None, depot_of: str | None) -> list[tuple[float, float]]:
            if route_id is None:
                d = self.depots[depot_of] if depot_of else next(iter(self.depots.values()))
                return [(d.lat, d.lon)]
            r = self.routes[route_id]
            return [(self.stops[s].lat, self.stops[s].lon) for s in (r.stop_ids[0], r.stop_ids[-1])]

        other = to_route if from_route is None else from_route
        depot = self.routes[other].depot_id if other else None
        best = min(
            haversine_km(a[0], a[1], b[0], b[1])
            for a in ends(from_route, depot)
            for b in ends(to_route, depot)
        )
        return round(1.3 * best, 1)


def build_route(row: dict, stop_rows: list[dict], shape_rows: list[dict]) -> Route:
    shape = np.array([[p["lat"], p["lon"]] for p in shape_rows], dtype=float)
    shape_km = np.array([p["dist_km"] for p in shape_rows], dtype=float)
    return Route(
        id=row["route_id"],
        name=row["route_long_name"],
        depot_id=row["depot_id"],
        color=row["route_color"],
        planned_headway_min=float(row["planned_headway_min"]),
        min_headway_min=float(row["min_headway_min"]),
        busy_factor=float(row["busy_factor"]),
        stop_ids=[s["stop_id"] for s in stop_rows],
        shape=shape,
        shape_km=shape_km,
        stop_km0=np.array([s["dist_km"] for s in stop_rows], dtype=float),
    )


def load_network(artefacts_dir: Path) -> Network:
    gtfs = artefacts_dir / "gtfs"
    cfg = json.loads((artefacts_dir / "config.json").read_text(encoding="utf-8"))
    stops = {
        r["stop_id"]: Stop(r["stop_id"], r["stop_name"], r["stop_lat"], r["stop_lon"], r["stop_type"])
        for r in pl.read_parquet(gtfs / "stops.parquet").iter_rows(named=True)
    }
    route_stops = pl.read_parquet(gtfs / "route_stops.parquet").filter(pl.col("direction_id") == 0)
    shapes = pl.read_parquet(gtfs / "shapes.parquet")
    routes: dict[str, Route] = {}
    for row in pl.read_parquet(gtfs / "routes.parquet").iter_rows(named=True):
        rs = route_stops.filter(pl.col("route_id") == row["route_id"]).sort("stop_seq").to_dicts()
        sh = shapes.filter(pl.col("shape_id") == row["route_id"]).sort("pt_seq").to_dicts()
        routes[row["route_id"]] = build_route(row, rs, sh)
    depots = {
        r["depot_id"]: Depot(r["depot_id"], r["name"], r["lat"], r["lon"], r["fleet_size"], r["reserve"], r["out_of_service"])
        for r in pl.read_parquet(gtfs / "depots.parquet").iter_rows(named=True)
    }
    return Network(
        stops=stops,
        routes=routes,
        depots=depots,
        config=cfg["network"],
        demand_params=cfg["demand"],
        scenarios=cfg["scenarios"],
    )
