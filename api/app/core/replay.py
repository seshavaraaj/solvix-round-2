"""Replay engine (plan B3.4): the in-memory clock and bus positions at time t.

Each scenario day is a set of per-bus timelines of stop events (recorded or
simulated, see offline/data_prep/build_replay.py). A bus position at t is
interpolated along the route shape between stop events, so the state is a
pure function of (scenario, t, approved changes).

Approved recommendations (plan B4.7) edit the timelines from the approval
time onward: moved buses finish their trip, deadhead, and run trips on the
new route; loads on both routes are rescaled by the change in bus count.
"""
from __future__ import annotations

import copy
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import polars as pl

from .demand import DemandModel
from .loads import segment_flow
from .network import Network, bearing_deg, haversine_km
from .timeutil import day_type, hhmm_to_s
from .traveltime import TravelTime

SPEEDS = (1, 10, 30)
DARK_AFTER_S = 120


@dataclass
class Leg:
    """Deadhead leg (no passengers) between two points."""
    t0: float
    t1: float
    lat0: float
    lon0: float
    lat1: float
    lon1: float
    route_id: str | None           # route the bus is heading to (None = depot)


@dataclass
class Timeline:
    bus_id: str
    route: np.ndarray
    direction: np.ndarray
    seq: np.ndarray
    arr: np.ndarray
    dep: np.ndarray
    sched: np.ndarray
    load: np.ndarray
    trip: np.ndarray
    legs: list[Leg] = field(default_factory=list)
    start_s: float | None = None   # reserve bus appears at this time
    end_s: float | None = None     # released bus disappears at this time
    broken_at: float | None = None
    depot_id: str | None = None

    def cut_after(self, k: int) -> None:
        for name in ("route", "direction", "seq", "arr", "dep", "sched", "load", "trip"):
            setattr(self, name, getattr(self, name)[: k + 1])

    def append(self, other: dict) -> None:
        for name, values in other.items():
            setattr(self, name, np.concatenate([getattr(self, name), values]))


@dataclass
class BusState:
    id: str
    route_id: str
    direction: int
    lat: float
    lon: float
    bearing: float
    load_factor: float
    delay_min: float
    dark: bool
    last_seen_s: float
    stop_seq: int
    in_service: bool
    deadhead: bool = False
    km: float = 0.0


@dataclass
class Mod:
    rec_id: str
    kind: str
    from_route: str | None
    to_route: str | None
    count: int
    t_s: float
    bus_ids: list[str] = field(default_factory=list)
    scale: dict[str, float] = field(default_factory=dict)   # route -> load multiplier
    t_eff: float = 0.0


class ReplayDay:
    def __init__(self, path: Path):
        self.meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        ev = pl.read_parquet(path / "events.parquet").sort(["bus_id", "arr_s"])
        self.timelines: dict[str, Timeline] = {}
        for (bus_id,), g in ev.group_by(["bus_id"], maintain_order=True):
            self.timelines[bus_id] = Timeline(
                bus_id=bus_id,
                route=g["route_id"].to_numpy().astype(object),
                direction=g["direction"].to_numpy().astype(np.int8),
                seq=g["stop_seq"].to_numpy().astype(np.int16),
                arr=g["arr_s"].to_numpy().astype(float),
                dep=g["dep_s"].to_numpy().astype(float),
                sched=g["sched_s"].to_numpy().astype(float),
                load=g["load_est"].to_numpy().astype(float),
                trip=g["trip_id"].to_numpy().astype(object),
            )
        for b in self.meta.get("breakdowns", []):
            if b["bus_id"] in self.timelines:
                self.timelines[b["bus_id"]].broken_at = float(b["t_s"])
        self.dark: dict[str, list[tuple[float, float]]] = {}
        for r in pl.read_parquet(path / "dark.parquet").iter_rows(named=True):
            self.dark.setdefault(r["bus_id"], []).append((float(r["start_s"]), float(r["end_s"])))
        # boardings (ETM stand-in) for the forecast lag features
        self.boardings = ev.select(["route_id", "direction", "stop_seq", "dep_s", "boardings"])
        self.segments = (ev.sort(["trip_id", "stop_seq"])
                         .with_columns(pl.col("arr_s").shift(-1).over("trip_id").alias("next_arr"),
                                       pl.col("stop_seq").shift(-1).over("trip_id").alias("next_seq"))
                         .filter(pl.col("next_seq") == pl.col("stop_seq") + 1)
                         .select(["bus_id", "route_id", "direction", "stop_seq", "dep_s",
                                  (pl.col("next_arr") - pl.col("dep_s")).alias("run_s")]))

    @property
    def date(self) -> str:
        return self.meta["date"]

    @property
    def window(self) -> tuple[int, int]:
        return int(self.meta["window_start_s"]), int(self.meta["window_end_s"])


class Clock:
    """In-memory replay clock (contract §6 rows 4–5). Resets on restart."""

    def __init__(self, scenario: str, start_s: float, window: tuple[int, int]):
        self._lock = threading.Lock()
        self.scenario = scenario
        self.window = window
        self._t = float(start_s)
        self._anchor = time.monotonic()
        self.speed = 10
        self.playing = False

    def now(self) -> float:
        with self._lock:
            return self._now_locked()

    def _now_locked(self) -> float:
        if not self.playing:
            return self._t
        t = self._t + (time.monotonic() - self._anchor) * self.speed
        if t >= self.window[1]:
            self._t, self.playing = float(self.window[1]), False
            return self._t
        return t

    def set(self, *, playing: bool | None = None, speed: int | None = None, t: float | None = None,
            scenario: str | None = None, window: tuple[int, int] | None = None) -> None:
        with self._lock:
            self._t = self._now_locked()
            self._anchor = time.monotonic()
            if scenario is not None:
                self.scenario = scenario
            if window is not None:
                self.window = window
            if t is not None:
                self._t = float(min(max(t, self.window[0]), self.window[1]))
            if speed is not None:
                self.speed = int(speed)
            if playing is not None:
                self.playing = bool(playing)


class Replay:
    def __init__(self, net: Network, dm: DemandModel, tt: TravelTime, replay_dir: Path, default_scenario: str):
        self.net, self.dm, self.tt = net, dm, tt
        self.days = {p.name: ReplayDay(p) for p in sorted(replay_dir.iterdir()) if (p / "meta.json").exists()}
        if not self.days:
            raise RuntimeError(f"no replay days in {replay_dir}")
        scen = default_scenario if default_scenario in self.days else next(iter(self.days))
        day = self.days[scen]
        self.clock = Clock(scen, day.meta["clock_start_s"], day.window)
        self._lock = threading.RLock()
        self.current: dict[str, dict[str, Timeline]] = {}
        self.mods: dict[str, list[Mod]] = {}
        self.version = 0
        for name in self.days:
            self.reset(name)

    # ---- scenario state -------------------------------------------------------------
    def reset(self, scenario: str) -> None:
        with self._lock:
            self.current[scenario] = {k: copy.copy(v) for k, v in self.days[scenario].timelines.items()}
            self.mods[scenario] = []
            self.version += 1

    def day(self, scenario: str | None = None) -> ReplayDay:
        return self.days[scenario or self.clock.scenario]

    def scenario_params(self, scenario: str | None = None) -> dict:
        d = self.day(scenario)
        sc = self.net.scenarios["scenarios"][d.meta["scenario"]]
        return {
            "date": d.date, "day_type": day_type(d.date, self.net.config.get("holidays", [])),
            "rain_mm": float(sc["rain_mm"]), "temp_c": float(sc["temp_c"]), "events": self.dm.events_for(sc),
            "breakdowns": [{"route_id": b["route_id"], "at_s": hhmm_to_s(b["at"])} for b in sc.get("breakdowns", [])],
            "speed_factor": self.tt.rain_speed_factor(float(sc["rain_mm"])),
        }

    # ---- positions ----------------------------------------------------------------------
    def _state_at(self, tl: Timeline, t: float, scale: dict[str, float]) -> BusState | None:
        if tl.start_s is not None and t < tl.start_s:
            return None
        if tl.end_s is not None and t >= tl.end_s:
            return None
        broken = tl.broken_at is not None and t >= tl.broken_at
        if broken:
            t_pos = tl.broken_at
        else:
            t_pos = t
        for leg in tl.legs:
            if leg.t0 <= t_pos < leg.t1:
                f = (t_pos - leg.t0) / max(1.0, leg.t1 - leg.t0)
                lat = leg.lat0 + f * (leg.lat1 - leg.lat0)
                lon = leg.lon0 + f * (leg.lon1 - leg.lon0)
                return BusState(tl.bus_id, leg.route_id or "", 0, lat, lon,
                                round(bearing_deg(leg.lat0, leg.lon0, leg.lat1, leg.lon1)), 0.0, 0.0, False, t,
                                0, leg.route_id is not None, deadhead=True)
        n = len(tl.arr)
        if n == 0:
            return None
        k = int(np.searchsorted(tl.arr, t_pos, side="right")) - 1
        k = max(k, 0)
        rid = str(tl.route[k])
        route = self.net.routes[rid]
        d = int(tl.direction[k])
        km_stops = route.stop_km(d)
        s = int(tl.seq[k])
        if t_pos <= tl.dep[k] or t_pos < tl.arr[k]:
            km = km_stops[s]
        elif k + 1 < n and tl.trip[k + 1] == tl.trip[k]:
            s2 = int(tl.seq[k + 1])
            f = (t_pos - tl.dep[k]) / max(1.0, tl.arr[k + 1] - tl.dep[k])
            km = km_stops[s] + min(max(f, 0.0), 1.0) * (km_stops[s2] - km_stops[s])
        else:
            km = km_stops[s]
        lat, lon, bearing = route.point_at(d, km)
        if broken:
            delay = (t - tl.sched[k]) / 60 if t > tl.sched[k] else 0.0
        else:
            delay = (tl.dep[k] - tl.sched[k]) / 60 if t_pos >= tl.dep[k] else (t_pos - tl.sched[k]) / 60
        load = tl.load[k] / self.net.capacity * scale.get(rid, 1.0)
        return BusState(tl.bus_id, rid, d, lat, lon, bearing, round(float(load), 2), round(float(max(delay, 0.0)), 1),
                        False, t, s, not broken, km=float(km))

    def route_scale(self, scenario: str, t: float) -> dict[str, float]:
        out: dict[str, float] = {}
        for m in self.mods.get(scenario, []):
            if t >= m.t_eff:
                for r, f in m.scale.items():
                    out[r] = out.get(r, 1.0) * f
        return out

    def states(self, t: float, scenario: str | None = None) -> list[BusState]:
        scenario = scenario or self.clock.scenario
        with self._lock:
            tls = self.current[scenario]
            scale = self.route_scale(scenario, t)
            dark = self.days[scenario].dark
            out = []
            for bus_id, tl in tls.items():
                st = self._state_at(tl, t, scale)
                if st is None:
                    continue
                for s0, s1 in dark.get(bus_id, ()):
                    if s0 <= t < s1:
                        prev = self._state_at(tl, s0, scale) or st
                        prev.dark = t - s0 > DARK_AFTER_S
                        prev.last_seen_s = s0
                        st = prev
                        break
                out.append(st)
            return out

    def fleet(self, t: float, scenario: str | None = None) -> dict[str, int]:
        """Buses in service (or deadheading to a route) per route at t."""
        out = {rid: 0 for rid in self.net.routes}
        for s in self.states(t, scenario):
            if s.in_service and s.route_id in out:
                out[s.route_id] += 1
        return out

    # ---- approved changes ---------------------------------------------------------
    def _synth_trips(self, route_id: str, direction: int, t0: float, until: float, headway_min: float,
                     speed_factor: float, events: list[dict]) -> dict:
        r = self.net.routes[route_id]
        cols = {k: [] for k in ("route", "direction", "seq", "arr", "dep", "sched", "load", "trip")}
        t, d, k = t0, direction, 0
        while t < until:
            minute = t / 60
            seg = self.tt.seg_times_s(route_id, d, minute, speed_factor)
            rate = self.dm.board_rate(route_id, d, minute, events=events)
            flow = segment_flow(rate, self.dm.dest_probs(route_id, d, minute))
            onboard = np.append(flow * headway_min, 0.0)
            trip = f"synth_{route_id}_{int(t0)}_{k}"
            for i in range(len(r.stop_ids)):
                dwell = self.tt.dwell_min if 0 < i < len(r.stop_ids) - 1 else 0.0
                cols["route"].append(route_id)
                cols["direction"].append(d)
                cols["seq"].append(i)
                cols["arr"].append(t)
                cols["dep"].append(t + dwell)
                cols["sched"].append(t + dwell)
                cols["load"].append(float(min(onboard[i], self.net.capacity_crush)))
                cols["trip"].append(trip)
                t += dwell + (seg[i] if i < len(seg) else 0.0)
            t += self.net.layover_min * 60
            d, k = 1 - d, k + 1
        return {
            "route": np.array(cols["route"], dtype=object), "direction": np.array(cols["direction"], dtype=np.int8),
            "seq": np.array(cols["seq"], dtype=np.int16), "arr": np.array(cols["arr"]),
            "dep": np.array(cols["dep"]), "sched": np.array(cols["sched"]), "load": np.array(cols["load"]),
            "trip": np.array(cols["trip"], dtype=object),
        }

    def apply(self, rec_id: str, kind: str, from_route: str | None, to_route: str | None, count: int,
              t: float, scenario: str | None = None) -> Mod:
        scenario = scenario or self.clock.scenario
        params = self.scenario_params(scenario)
        _, w1 = self.days[scenario].window
        until = w1 + 1800
        with self._lock:
            tls = self.current[scenario]
            fleet = self.fleet(t, scenario)
            mod = Mod(rec_id, kind, from_route, to_route, count, t, t_eff=t)
            n_to = fleet.get(to_route, 0) if to_route else 0
            n_from = fleet.get(from_route, 0) if from_route else 0
            h_new = (self.tt.cycle_min(to_route, t / 60, params["speed_factor"]) / max(1, n_to + count)
                     if to_route else 0.0)
            arrive_times = []
            if from_route is None:
                depot = self.net.depots[self.net.routes[to_route].depot_id]
                for i in range(count):
                    bus_id = f"bus_DL1PR{len([b for b in tls if b.startswith('bus_DL1PR')]) + 1:02d}"
                    tl = Timeline(bus_id, *(np.array([], dtype=dt) for dt in (object, np.int8, np.int16)),
                                  *(np.array([]) for _ in range(4)), np.array([], dtype=object),
                                  start_s=t + i * 60, depot_id=depot.id)
                    t_arr = self._route_bus_to(tl, depot.lat, depot.lon, t + i * 60, to_route, h_new, until, params)
                    tls[bus_id] = tl
                    mod.bus_ids.append(bus_id)
                    arrive_times.append(t_arr)
            else:
                cands = []
                for bus_id, tl in tls.items():
                    st = self._state_at(tl, t, {})
                    if st is None or not st.in_service or st.deadhead or st.route_id != from_route:
                        continue
                    last = len(self.net.routes[from_route].stop_ids) - 1
                    idx = np.nonzero((tl.arr >= t) & (tl.seq == last))[0]
                    if len(idx):
                        cands.append((tl.arr[idx[0]], int(idx[0]), bus_id))
                cands.sort()
                for t_end, k, bus_id in cands[: min(count, max(0, n_from - 1))]:
                    tl = copy.copy(tls[bus_id])
                    tl.legs = list(tl.legs)
                    route = self.net.routes[str(tl.route[k])]
                    end_stop = self.net.stops[route.stops(int(tl.direction[k]))[-1]]
                    tl.cut_after(k)
                    if to_route is None:
                        depot = self.net.depots[route.depot_id]
                        dh = 1.3 * haversine_km(end_stop.lat, end_stop.lon, depot.lat, depot.lon)
                        t1 = t_end + 60 + dh / float(self.net.config["deadhead_speed_kmh"]) * 3600
                        tl.legs.append(Leg(t_end + 60, t1, end_stop.lat, end_stop.lon, depot.lat, depot.lon, None))
                        tl.end_s = t1
                        arrive_times.append(t_end)
                    else:
                        arrive_times.append(self._route_bus_to(tl, end_stop.lat, end_stop.lon, t_end + 60, to_route,
                                                               h_new, until, params))
                    tls[bus_id] = tl
                    mod.bus_ids.append(bus_id)
            moved = len(mod.bus_ids)
            mod.count = moved
            if moved:
                mod.t_eff = float(np.median(arrive_times))
                if to_route and n_to:
                    mod.scale[to_route] = n_to / (n_to + moved)
                if from_route and n_from > moved:
                    mod.scale[from_route] = n_from / (n_from - moved)
            self.mods[scenario].append(mod)
            self.version += 1
            return mod

    def _route_bus_to(self, tl: Timeline, lat: float, lon: float, t0: float, to_route: str, headway_min: float,
                      until: float, params: dict) -> float:
        route = self.net.routes[to_route]
        best = min((0, 1), key=lambda d: haversine_km(lat, lon, self.net.stops[route.terminal(d)].lat,
                                                      self.net.stops[route.terminal(d)].lon))
        term = self.net.stops[route.terminal(best)]
        dh = 1.3 * haversine_km(lat, lon, term.lat, term.lon)
        t1 = t0 + dh / float(self.net.config["deadhead_speed_kmh"]) * 3600
        tl.legs.append(Leg(t0, t1, lat, lon, term.lat, term.lon, to_route))
        tl.append(self._synth_trips(to_route, best, t1, until, headway_min, params["speed_factor"], params["events"]))
        return t1

    # ---- observations for detection and forecasting ---------------------------------
    def observed_boardings(self, t: float, since_s: float, scenario: str | None = None) -> pl.DataFrame:
        b = self.day(scenario).boardings
        return b.filter((pl.col("dep_s") >= since_s) & (pl.col("dep_s") < t))

    def observed_segments(self, t: float, since_s: float, scenario: str | None = None) -> pl.DataFrame:
        s = self.day(scenario).segments
        return s.filter((pl.col("dep_s") >= since_s) & (pl.col("dep_s") + pl.col("run_s") <= t))

    def last_departures(self, t: float, scenario: str | None = None) -> dict[tuple[str, int, int], list[tuple[float, str]]]:
        """(route, direction, stop_seq) -> sorted [(dep_s, bus_id)] for the last 60 minutes."""
        scenario = scenario or self.clock.scenario
        out: dict[tuple[str, int, int], list[tuple[float, str]]] = {}
        with self._lock:
            for bus_id, tl in self.current[scenario].items():
                if len(tl.dep) == 0:
                    continue
                lim = t if tl.broken_at is None else min(t, tl.broken_at)
                mask = (tl.dep <= lim) & (tl.dep > t - 3600)
                for k in np.nonzero(mask)[0]:
                    out.setdefault((str(tl.route[k]), int(tl.direction[k]), int(tl.seq[k])), []).append(
                        (float(tl.dep[k]), bus_id))
        for v in out.values():
            v.sort()
        return out

    def shift_end(self, scenario: str | None = None) -> dict[str, int]:
        return self.day(scenario).meta.get("shift_end_s", {})

    def speed_ok(self, speed: int) -> bool:
        return speed in SPEEDS

    def window(self, scenario: str | None = None) -> tuple[int, int]:
        return self.day(scenario).window

