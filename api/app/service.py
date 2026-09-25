"""Application state: loads artefacts once at start-up and answers the
questions the routers ask (state at t, route health, ETA, alerts)."""
from __future__ import annotations

import hashlib
import json
import threading
import time
import traceback
from dataclasses import dataclass

import numpy as np
import polars as pl
from sqlalchemy import select

from . import db
from .config import settings
from .core.crowding import CrowdingStore, Report
from .core.demand import DemandModel
from .core.detect import Flag, bunching, delay_emerging, overcrowded, route_health, underused
from .core.forecast import Forecaster, ForecastView
from .core.network import Network, load_network
from .core.replay import BusState, Replay
from .core.timeutil import hhmm, parse_iso, to_iso
from .core.traveltime import TravelTime

VIEW_BUCKET_S = 300


@dataclass
class Analysis:
    t_s: float
    health: list[dict]
    flags: dict[tuple[str, int], dict[str, Flag]]
    lf: dict[tuple[str, int], tuple[np.ndarray, np.ndarray]]
    fleet: dict[str, int]
    view: ForecastView
    crowd_scale: dict[str, float]


class AppState:
    def __init__(self) -> None:
        self.ready = False
        self.error: str | None = None
        self.models_loaded = False
        self.net: Network | None = None
        self.dm: DemandModel | None = None
        self.tt: TravelTime | None = None
        self.forecaster: Forecaster | None = None
        self.replay: Replay | None = None
        self.crowding = CrowdingStore()
        self.routes_cfg: dict[str, dict] = {}
        self.fleet_cfg: dict[str, dict] = {}
        self.results: dict | None = None
        self.cycle_cache: dict[str, dict] = {}
        self.first_seen: dict[tuple, float] = {}
        self._views: dict[tuple, ForecastView] = {}
        self.lock = threading.RLock()
        self.load_seconds: float | None = None

    # ---- start-up -----------------------------------------------------------------------
    def load(self) -> None:
        t0 = time.perf_counter()
        try:
            art = settings.artefacts_dir
            self.net = load_network(art)
            self.tt = TravelTime(self.net)
            self.dm = DemandModel(self.net, self.tt)
            self.forecaster = Forecaster(self.net, self.dm, self.tt, art / "models")
            self.models_loaded = self.forecaster.loaded
            self.replay = Replay(self.net, self.dm, self.tt, art / "replay", settings.default_scenario)
            results = art / "results.json"
            self.results = json.loads(results.read_text(encoding="utf-8")) if results.exists() else None
            self._load_db()
            self.load_seconds = round(time.perf_counter() - t0, 2)
            self.ready = True
        except Exception as exc:  # keep /health answering; show the error there
            self.error = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()

    def _load_db(self) -> None:
        self.routes_cfg = {rid: self.route_json_from_network(rid) for rid in self.net.routes}
        self.fleet_cfg = {d.id: {"depot_id": d.id, "name": d.name, "lat": d.lat, "lon": d.lon,
                                 "fleet_size": d.fleet_size, "reserve": d.reserve, "out_of_service": d.out_of_service}
                          for d in self.net.depots.values()}
        try:
            db.create_all()
            with db.engine().begin() as c:
                for row in c.execute(select(db.routes_config)).mappings():
                    self.routes_cfg[row["route_id"]] = json.loads(row["payload"])
                for row in c.execute(select(db.fleet_config)).mappings():
                    self.fleet_cfg[row["depot_id"]] = {k: row[k] for k in ("depot_id", "name", "lat", "lon",
                                                                            "fleet_size", "reserve", "out_of_service")}
                cutoff = time.time() - 2 * 3600
                reps = [Report(r["device_id"], r["bus_id"], r["route_id"], r["level"], r["received_ts"])
                        for r in c.execute(select(db.crowding_reports)
                                           .where(db.crowding_reports.c.received_ts >= cutoff)).mappings()]
                self.crowding.load(reps)
        except Exception as exc:
            print(f"database not available at start-up: {exc}")
        self.apply_admin_config()

    def apply_admin_config(self) -> None:
        """Admin edits that feed the optimiser: min frequency and depot fleet."""
        for rid, cfg in self.routes_cfg.items():
            if rid in self.net.routes:
                self.net.routes[rid].min_headway_min = float(cfg.get("min_headway_min",
                                                                     self.net.routes[rid].min_headway_min))
        for dep_id, cfg in self.fleet_cfg.items():
            d = self.net.depots.get(dep_id)
            if d is not None:
                d.fleet_size, d.reserve, d.out_of_service = cfg["fleet_size"], cfg["reserve"], cfg["out_of_service"]

    def route_json_from_network(self, rid: str) -> dict:
        r = self.net.routes[rid]
        return {
            "id": r.id, "name": r.name, "depot_id": r.depot_id, "color": r.color,
            "min_headway_min": r.min_headway_min, "shape": r.geojson(),
            "stops": [{"id": s, "name": self.net.stops[s].name, "lat": self.net.stops[s].lat,
                       "lon": self.net.stops[s].lon, "seq": i} for i, s in enumerate(r.stop_ids)],
        }

    # ---- time helpers ---------------------------------------------------------------------
    @property
    def scenario(self) -> str:
        return self.replay.clock.scenario

    def now_s(self) -> float:
        return self.replay.clock.now()

    def iso(self, t_s: float) -> str:
        return to_iso(self.replay.day().date, t_s)

    def parse_t(self, t: str | None) -> float:
        if not t:
            return self.now_s()
        _, s = parse_iso(t)
        w0, w1 = self.replay.window()
        return float(min(max(s, w0), w1))

    # ---- buses ------------------------------------------------------------------------------
    def bus_json(self, s: BusState) -> dict:
        lf = self.crowding.bus_lf(s.id, s.load_factor) if self.crowding.for_bus(s.id) else s.load_factor
        return {"id": s.id, "route_id": s.route_id, "direction": s.direction, "lat": round(s.lat, 6),
                "lon": round(s.lon, 6), "bearing": float(s.bearing), "load_factor": round(lf, 2),
                "delay_min": s.delay_min, "dark": s.dark, "last_seen": self.iso(s.last_seen_s)}

    def visible_states(self, t: float) -> list[BusState]:
        return [s for s in self.replay.states(t) if s.route_id]

    def feed(self, states: list[BusState]) -> dict:
        expected = [s for s in states if s.in_service]
        reporting = [s for s in expected if not s.dark]
        n = len(expected)
        return {"buses_expected": n, "buses_reporting": len(reporting),
                "share_reporting": round(len(reporting) / n, 3) if n else 1.0, "mode": "replay", "fresh": True}

    # ---- analysis -----------------------------------------------------------------------------
    def forecast_view(self, t: float) -> ForecastView:
        bucket = int(t // VIEW_BUCKET_S)
        key = (self.scenario, bucket, self.replay.version)
        with self.lock:
            v = self._views.get(key)
            if v is None:
                p = self.replay.scenario_params()
                tb = bucket * VIEW_BUCKET_S
                obs = self.replay.observed_boardings(tb, tb - 3600)
                v = self.forecaster.view(tb, p["date"], p["day_type"] == "holiday", p["rain_mm"], p["temp_c"],
                                         p["events"], obs)
                if len(self._views) > 64:
                    self._views.clear()
                self._views[key] = v
            return v

    def analyse(self, t: float, states: list[BusState] | None = None) -> Analysis:
        net, tt = self.net, self.tt
        p = self.replay.scenario_params()
        states = states if states is not None else self.visible_states(t)
        prev = {s.id: s for s in self.visible_states(max(t - 900, 0))}
        fleet = {rid: 0 for rid in net.routes}
        for s in states:
            if s.in_service and s.route_id in fleet:
                fleet[s.route_id] += 1
        view = self.forecast_view(t)
        seg_obs = self.replay.observed_segments(t, t - 1800)
        deps = self.replay.last_departures(t)
        health, flags_out, lf_out, crowd_scale = [], {}, {}, {}
        for rid, r in net.routes.items():
            on_route = [s for s in states if s.route_id == rid and s.in_service and not s.deadhead]
            mean_lf = float(np.mean([s.load_factor for s in on_route])) if on_route else 0.0
            crowd_scale[rid] = self.crowding.route_scale(rid, mean_lf)
            n = max(1, fleet[rid])
            cycle = tt.cycle_min(rid, t / 60, p["speed_factor"])
            headway = cycle / n
            for d in (0, 1):
                names = [net.stops[sid].name for sid in r.stops(d)]
                bus_d = [s for s in on_route if s.direction == d]
                dark_d = [s for s in bus_d if s.dark]
                lf50, lf90 = self.forecaster.segment_loads(view, rid, d, headway, crowd_scale[rid])
                band_starts = [(view.now_band + h) * 900 for h in range(1, 5)]
                f_over = overcrowded(lf50.tolist(), lf90.tolist(), names[:-1], band_starts, dark=bool(dark_d))
                f_under = underused(lf50.tolist(), lf90.tolist(), band_starts, dark=bool(dark_d))
                # delay emerging
                obs = seg_obs.filter((pl.col("route_id") == rid) & (pl.col("direction") == d))
                segs = []
                if obs.height:
                    recent = obs.group_by("stop_seq").agg(pl.col("run_s").mean().alias("m"), pl.len().alias("n"))
                    expected = self.forecaster.segment_times(rid, d, t, p["date"], p["rain_mm"])
                    for row in recent.iter_rows(named=True):
                        i = int(row["stop_seq"])
                        if i < len(expected):
                            segs.append({"name": f"{names[i]} → {names[i + 1]}", "observed_s": float(row["m"]),
                                         "expected_s": float(expected[i]), "n": int(row["n"])})
                delay_now = float(np.mean([s.delay_min for s in bus_d])) if bus_d else 0.0
                prev_d = [prev[s.id].delay_min for s in bus_d if s.id in prev]
                delay_prev = float(np.mean(prev_d)) if prev_d else delay_now
                f_delay = delay_emerging(segs, delay_now, delay_prev, tt.noise_cv, dark=bool(dark_d))
                # bunching: headway between consecutive departures at each bus's last stop
                hws = []
                dark_ids = {s.id for s in dark_d}
                for s in bus_d:
                    lst = deps.get((rid, d, s.stop_seq), [])
                    idx = next((i for i, (_, b) in enumerate(lst) if b == s.id), None)
                    if idx:
                        t_prev, b_prev = lst[idx - 1]
                        hws.append({"headway_min": (lst[idx][0] - t_prev) / 60, "stop": names[s.stop_seq],
                                    "dark": s.id in dark_ids or b_prev in dark_ids})
                f_bunch = bunching(hws, headway, len(dark_d))
                fl = {"overcrowded": f_over, "underused": f_under, "delay_emerging": f_delay, "bunching": f_bunch}
                flags_out[rid, d] = fl
                lf_out[rid, d] = (lf50, lf90)
                health.append(route_health(rid, d, fl))
                for k, f in fl.items():
                    key = (self.scenario, rid, d, k)
                    if f.on:
                        self.first_seen.setdefault(key, t)
                    else:
                        self.first_seen.pop(key, None)
        return Analysis(t, health, flags_out, lf_out, fleet, view, crowd_scale)

    # ---- queries ------------------------------------------------------------------------------
    def eta(self, stop_id: str, route_id: str | None) -> list[dict]:
        t = self.now_s()
        p = self.replay.scenario_params()
        out = []
        cache: dict[tuple[str, int], np.ndarray] = {}
        for s in self.visible_states(t):
            if not s.in_service or s.deadhead or (route_id and s.route_id != route_id):
                continue
            r = self.net.routes.get(s.route_id)
            if r is None:
                continue
            stops = r.stops(s.direction)
            if stop_id not in stops:
                continue
            j = stops.index(stop_id)
            km = r.stop_km(s.direction)
            if km[j] <= s.km + 1e-6:
                continue
            key = (s.route_id, s.direction)
            if key not in cache:
                cache[key] = self.forecaster.segment_times(s.route_id, s.direction, t, p["date"], p["rain_mm"])
            seg = cache[key]
            i = int(np.searchsorted(km, s.km, side="right")) - 1
            i = min(max(i, 0), len(seg) - 1)
            frac_left = (km[i + 1] - s.km) / max(1e-6, km[i + 1] - km[i])
            secs = seg[i] * frac_left + seg[i + 1:j].sum() + self.tt.dwell_min * max(0, j - i - 1)
            lf = self.crowding.bus_lf(s.id, s.load_factor) if self.crowding.for_bus(s.id) else s.load_factor
            out.append({"bus_id": s.id, "route_id": s.route_id, "eta_min": round(float(secs) / 60, 1),
                        "load_factor": round(lf, 2)})
        return sorted(out, key=lambda x: x["eta_min"])[:10]

    def alerts(self, route_id: str | None) -> list[dict]:
        t = self.now_s()
        a = self.analyse(t)
        out = []

        seen: set[tuple[str, str]] = set()

        def add(rid: str, kind: str, message: str, since_s: float, key: str) -> None:
            if route_id and rid != route_id:
                return
            if kind != "service_change":          # one alert per route and kind, both directions
                if (rid, kind) in seen:
                    return
                seen.add((rid, kind))
                key = f"{rid}|{kind}"
            aid = "al_" + hashlib.sha1(f"{self.scenario}|{key}".encode()).hexdigest()[:6]
            out.append({"id": aid, "route_id": rid, "kind": kind, "message": message, "since": self.iso(since_s)})

        for (rid, d), fl in a.flags.items():
            label = f"Route {rid}"
            if fl["delay_emerging"].on:
                dm = fl["delay_emerging"].detail.get("delay_min") or 0
                seg = fl["delay_emerging"].detail.get("segment")
                where = f" near {seg.split(' → ')[0]}" if seg else ""
                msg = (f"{label} running about {max(1, round(dm))} minutes late{where}." if dm >= 1
                       else f"{label} is slower than usual{where}.")
                add(rid, "delay", msg, self.first_seen.get((self.scenario, rid, d, "delay_emerging"), t), f"{rid}|{d}|delay")
            if fl["bunching"].on:
                add(rid, "bunching", f"Buses on {label} are bunched; expect a longer wait, then two buses close together.",
                    self.first_seen.get((self.scenario, rid, d, "bunching"), t), f"{rid}|{d}|bunching")
            if fl["overcrowded"].on:
                det = fl["overcrowded"].detail
                add(rid, "crowded", f"{label} is expected to be very crowded near {det['stop']} until {hhmm(det['to_s'])}.",
                    self.first_seen.get((self.scenario, rid, d, "overcrowded"), t), f"{rid}|{d}|crowded")
        for rec in self.approved_recs():
            p = rec
            t0, t1 = hhmm(parse_iso(p["window_start"])[1]), hhmm(parse_iso(p["window_end"])[1])
            since = parse_iso(p["created_at"])[1]
            if p["to_route_id"]:
                src = f" (moved from Route {p['from_route_id']})" if p["from_route_id"] else " (from the depot reserve)"
                add(p["to_route_id"], "service_change",
                    f"Extra bus{'es' if p['bus_count'] > 1 else ''} on Route {p['to_route_id']} {t0}–{t1}{src}.",
                    since, f"{p['id']}|to")
            if p["from_route_id"]:
                h = p["expected_effect"]["from_route"]["wait_min_after"] * 2 if p["expected_effect"]["from_route"] else None
                txt = f" Buses about every {round(h)} minutes." if h else ""
                add(p["from_route_id"], "service_change",
                    f"Route {p['from_route_id']} runs fewer buses {t0}–{t1}.{txt}", since, f"{p['id']}|from")
        return out

    def approved_recs(self) -> list[dict]:
        try:
            with db.engine().connect() as c:
                rows = c.execute(select(db.recommendations.c.payload).where(
                    (db.recommendations.c.scenario == self.scenario) & (db.recommendations.c.status == "approved")))
                return [json.loads(r[0]) for r in rows]
        except Exception:
            return []


state = AppState()
