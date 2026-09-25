"""SimPy discrete-event bus model (solution2 §6.11).

One code base serves three uses:
- offline batch: full service windows for every scenario x strategy x error;
- online what-if: one cluster, 2 hours, with vs without a recommendation;
- build_replay: generates the replay day when no GTFS-RT recording exists.

Passengers are simulated as groups: arrivals at a stop are generated lazily
(Poisson per 5-minute chunk) when a bus arrives, which keeps the event count
small enough for Render's 0.1 CPU.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import simpy

from ..core.demand import DemandModel
from ..core.network import Network
from ..core.traveltime import TravelTime

STRATEGIES = ("baseline", "holding", "aduthabus")
MIN_LAYOVER_S = 120.0
MAX_MID_HOLD_S = 180.0
TERMINAL_SPACING = 0.85       # aduthabus: depart >= 0.85 x headway after the previous bus
MID_SPACING = 0.7             # aduthabus: hold mid-route until 0.7 x headway after the previous bus
CHUNK_S = 300.0


@dataclass
class Move:
    at_s: float
    from_route: str | None          # None = depot reserve (add_trip)
    to_route: str | None            # None = back to depot (release_bus)
    count: int = 1
    deadhead_km: float = 0.0


@dataclass
class SimConfig:
    start_s: float
    end_s: float
    day_type: str = "weekday"
    rain_mm: float = 0.0
    events: list[dict] = field(default_factory=list)       # DemandModel event dicts (minutes)
    breakdowns: list[dict] = field(default_factory=list)   # [{"route_id", "at_s"}]
    fleet: dict[str, int] | None = None                    # buses per route at start
    reserve: dict[str, int] | None = None                  # usable reserve per depot
    strategy: str = "baseline"
    moves: list[Move] = field(default_factory=list)        # fixed moves (what-if "with")
    planner: Callable[["Simulation", float], list[Move]] | None = None
    planner_every_s: float = 1800.0
    demand_noise: dict[str, float] = field(default_factory=dict)  # true demand multiplier per route
    speed_noise_cv: float | None = None
    seed: int = 0
    warmup_s: float = 2700.0
    record: bool = False
    sample_every_s: float = 300.0
    routes: list[str] | None = None                        # restrict to a cluster subset


class Bus:
    __slots__ = ("id", "route_id", "direction", "onboard", "active", "broken", "reassign",
                 "trip_no", "stop_idx", "last_load", "depot_id", "trip_id")

    def __init__(self, bus_id: str, route_id: str, n_stops: int, depot_id: str):
        self.id = bus_id
        self.route_id = route_id
        self.direction = 0
        self.onboard = np.zeros(n_stops)
        self.active = True
        self.broken = False
        self.reassign: tuple[str, str | None] | None = None   # ("move", route) / ("release", None)
        self.trip_no = 0
        self.stop_idx = 0
        self.last_load = 0.0
        self.depot_id = depot_id
        self.trip_id = ""


def bus_ids_for(net: Network, fleet: dict[str, int]) -> dict[str, list[str]]:
    """Deterministic bus IDs so replay, simulator and API agree."""
    out: dict[str, list[str]] = {}
    k = 1000
    for rid in sorted(net.routes):
        out[rid] = [f"bus_DL1PC{k + i}" for i in range(fleet.get(rid, 0))]
        k += 100
    return out


def planned_fleet(net: Network, tt: TravelTime, minute: float = 18 * 60) -> dict[str, int]:
    return {rid: math.ceil(tt.cycle_min(rid, minute) / r.planned_headway_min) for rid, r in net.routes.items()}


class Simulation:
    def __init__(self, net: Network, demand: DemandModel, tt: TravelTime, cfg: SimConfig):
        self.net, self.demand, self.tt, self.cfg = net, demand, tt, cfg
        self.rng = np.random.default_rng(cfg.seed)
        self.env = simpy.Environment(initial_time=cfg.start_s - cfg.warmup_s)
        self.speed_factor = tt.rain_speed_factor(cfg.rain_mm)
        self.noise_cv = tt.noise_cv if cfg.speed_noise_cv is None else cfg.speed_noise_cv
        self.route_ids = cfg.routes or sorted(net.routes)
        fleet = cfg.fleet or planned_fleet(net, tt, cfg.start_s / 60)
        self.fleet = {r: fleet.get(r, 0) for r in self.route_ids}
        self.reserve = dict(cfg.reserve if cfg.reserve is not None else
                            {d.id: max(0, d.reserve - d.out_of_service) for d in net.depots.values()})
        self.buses: list[Bus] = []
        self.queues: dict[tuple[str, int, int], dict] = {}
        self.last_dep: dict[tuple[str, int, int], float] = {}
        self._rate_cache: dict[tuple, np.ndarray] = {}
        self._dest_cache: dict[tuple, np.ndarray] = {}
        # metrics
        self.wait_s: list[float] = []
        self.wait_n: list[float] = []
        self.left_behind = 0.0
        self.overload_min = 0.0
        self.bunching = 0
        self.lf_time = 0.0
        self.bus_time = 0.0
        self.deadhead_km = 0.0
        self.changes = 0
        self.moves_done: list[Move] = []
        self.events: list[dict] = []
        self.series: list[dict] = []
        self.route_stats: dict[str, dict] = {
            r: {"wait_s": 0.0, "wait_n": 0.0, "left_behind": 0.0, "overload_min": 0.0, "bunching": 0}
            for r in net.routes
        }
        self._next_reserve = 1
        self.breakdown_log: list[dict] = []

    # ---- demand helpers -------------------------------------------------------
    def _rate(self, route_id: str, direction: int, minute: float) -> np.ndarray:
        key = (route_id, direction, int(minute // 5))
        rate = self._rate_cache.get(key)
        if rate is None:
            rate = self.demand.board_rate(route_id, direction, (key[2] + 0.5) * 5, self.cfg.day_type,
                                          self.cfg.rain_mm, self.cfg.events)
            rate = rate * self.cfg.demand_noise.get(route_id, 1.0)
            self._rate_cache[key] = rate
        return rate

    def _dest(self, route_id: str, direction: int, minute: float) -> np.ndarray:
        key = (route_id, direction, int(minute // 60))
        m = self._dest_cache.get(key)
        if m is None:
            m = self.demand.dest_probs(route_id, direction, key[2] * 60 + 30)
            self._dest_cache[key] = m
        return m

    def _queue(self, route_id: str, direction: int, i: int) -> dict:
        key = (route_id, direction, i)
        q = self.queues.get(key)
        if q is None:
            q = {"t": self.cfg.start_s - self.cfg.warmup_s, "groups": deque()}
            self.queues[key] = q
        return q

    def _generate(self, route_id: str, direction: int, i: int, now: float) -> dict:
        q = self._queue(route_id, direction, i)
        t = q["t"]
        while t < now - 1e-9:
            t2 = min(now, (math.floor(t / CHUNK_S) + 1) * CHUNK_S)
            lam = self._rate(route_id, direction, (t + t2) / 120.0)[i] * (t2 - t) / 60.0
            n = self.rng.poisson(lam) if lam > 0 else 0
            if n:
                q["groups"].append([t, t2, float(n)])
            t = t2
        q["t"] = max(q["t"], now)
        return q

    def _board(self, q: dict, k_max: float, now: float, route_id: str) -> float:
        boarded = 0.0
        counted = now >= self.cfg.start_s
        groups = q["groups"]
        while groups and boarded < k_max - 1e-9:
            g = groups[0]
            m = min(g[2], k_max - boarded)
            frac = m / g[2]
            t_mid = g[0] + (g[1] - g[0]) * frac / 2
            if counted:
                w = max(0.0, now - t_mid)
                self.wait_s.append(w)
                self.wait_n.append(m)
                self.route_stats[route_id]["wait_s"] += w * m
                self.route_stats[route_id]["wait_n"] += m
            g[0] += (g[1] - g[0]) * frac
            g[2] -= m
            boarded += m
            if g[2] <= 1e-9:
                groups.popleft()
        return boarded

    # ---- schedule helpers -----------------------------------------------------
    def _norm_times(self, route_id: str, direction: int, minute: float) -> np.ndarray:
        """Scheduled departure offsets (s) from trip start at each stop."""
        seg = self.tt.seg_times_s(route_id, direction, minute)
        dwell = np.full(len(seg) + 1, self.tt.dwell_min)
        dwell[0] = 0.0
        return np.concatenate([[0.0], np.cumsum(seg + dwell[1:])])

    def headway_planned(self, route_id: str, now: float) -> float:
        n = sum(1 for b in self.buses if b.active and not b.broken and b.route_id == route_id) or 1
        return self.tt.cycle_min(route_id, now / 60) / n

    # ---- processes ---------------------------------------------------------------
    def _new_bus(self, bus_id: str, route_id: str) -> Bus:
        r = self.net.routes[route_id]
        bus = Bus(bus_id, route_id, len(r.stop_ids), r.depot_id)
        self.buses.append(bus)
        return bus

    def _place_initial(self) -> None:
        ids = bus_ids_for(self.net, self.fleet)
        t0 = self.env.now
        for rid in self.route_ids:
            n = self.fleet[rid]
            if n <= 0:
                continue
            m0 = t0 / 60
            r0 = self.tt.run_time_min(rid, 0, m0)
            r1 = self.tt.run_time_min(rid, 1, m0)
            lay = self.net.layover_min
            cycle = r0 + r1 + 2 * lay
            h = cycle / n
            for k in range(n):
                bus = self._new_bus(ids[rid][k], rid)
                phi = k * h
                if phi < r0:
                    self.env.process(self._run(bus, 0, t0 - phi * 60, mid_elapsed_s=phi * 60))
                elif phi < r0 + lay:
                    self.env.process(self._run(bus, 1, t0 + (r0 + lay - phi) * 60))
                elif phi < r0 + lay + r1:
                    el = (phi - r0 - lay) * 60
                    self.env.process(self._run(bus, 1, t0 - el, mid_elapsed_s=el))
                else:
                    self.env.process(self._run(bus, 0, t0 + (cycle - phi) * 60))

    def _run(self, bus: Bus, direction: int, sched_start: float, mid_elapsed_s: float = 0.0, fresh: bool = False):
        """Bus process: run trips back and forth until the end of the window."""
        env = self.env
        start_idx = 0
        if mid_elapsed_s > 0:
            norm = self._norm_times(bus.route_id, direction, sched_start / 60)
            start_idx = int(np.searchsorted(norm, mid_elapsed_s, side="right"))
            start_idx = min(start_idx, len(norm) - 1)
            yield env.timeout(max(0.0, sched_start + norm[start_idx] - env.now))
        elif sched_start > env.now:
            yield env.timeout(sched_start - env.now)
        if fresh:
            # slot a re-assigned bus into the largest gap instead of bunching
            key = (bus.route_id, direction, 0)
            h = self.headway_planned(bus.route_id, env.now) * 60
            last = self.last_dep.get(key)
            if last is not None and env.now < last + h * 0.8:
                yield env.timeout(last + h * 0.8 - env.now)
            sched_start = env.now
        while env.now < self.cfg.end_s and bus.active:
            yield from self._trip(bus, direction, sched_start, start_idx)
            if bus.broken or not bus.active:
                return
            start_idx = 0
            if bus.reassign is not None:
                yield from self._reassign(bus, direction)
                return
            nxt = 1 - direction
            norm = self._norm_times(bus.route_id, direction, sched_start / 60)
            sched_start = sched_start + norm[-1] + self.net.layover_min * 60
            earliest = env.now + MIN_LAYOVER_S
            if sched_start < earliest:
                sched_start_actual = earliest
            else:
                sched_start_actual = sched_start
            yield env.timeout(sched_start_actual - env.now)
            direction = nxt

    def _trip(self, bus: Bus, direction: int, sched_start: float, start_idx: int):
        env = self.env
        r = self.net.routes[bus.route_id]
        stops = r.stops(direction)
        n = len(stops)
        bus.direction = direction
        bus.trip_no += 1
        bus.trip_id = f"{bus.id}_{bus.route_id}_{int(sched_start)}_{direction}"
        if len(bus.onboard) != n:
            bus.onboard = np.zeros(n)
        norm = self._norm_times(bus.route_id, direction, sched_start / 60)
        mid = n // 2
        hold = self.cfg.strategy == "holding"
        headway_ctl = self.cfg.strategy == "aduthabus"
        for i in range(start_idx, n):
            if bus.broken:
                return
            bus.stop_idx = i
            now = env.now
            minute = now / 60
            alight = bus.onboard[i]
            bus.onboard[i] = 0.0
            boarded = 0.0
            if i < n - 1:
                q = self._generate(bus.route_id, direction, i, now)
                room = self.net.capacity_crush - bus.onboard.sum()
                waiting = sum(g[2] for g in q["groups"])
                boarded = self._board(q, max(0.0, min(room, waiting)), now, bus.route_id)
                denied = waiting - boarded
                if denied > 0.5 and now >= self.cfg.start_s:
                    self.left_behind += denied
                    self.route_stats[bus.route_id]["left_behind"] += denied
                if boarded > 0:
                    k = int(round(boarded))
                    if k > 0:
                        bus.onboard += self.rng.multinomial(k, self._dest(bus.route_id, direction, minute)[i])
            dwell = self.tt.dwell_s(boarded, alight) if 0 < i < n - 1 else 0.0
            dep = now + dwell
            sched = sched_start + norm[i]
            key = (bus.route_id, direction, i)
            if headway_ctl and i in (0, mid):
                # headway-based dispatching: re-spaces the route after every fleet change
                prev = self.last_dep.get(key)
                h = self.headway_planned(bus.route_id, now) * 60
                if i == 0:
                    dep = max(dep, prev + TERMINAL_SPACING * h if prev is not None else sched)
                elif prev is not None and dep < prev + MID_SPACING * h:
                    dep = min(prev + MID_SPACING * h, dep + MAX_MID_HOLD_S)
            elif i == 0:
                dep = max(dep, sched)
            elif hold and i == mid and dep < sched:
                dep = min(sched, dep + MAX_MID_HOLD_S)
            if dep > now:
                yield env.timeout(dep - now)
            load = float(bus.onboard.sum())
            bus.last_load = load / self.net.capacity
            if i < n - 1:
                prev = self.last_dep.get(key)
                if prev is not None and env.now >= self.cfg.start_s:
                    if (env.now - prev) < 0.5 * self.headway_planned(bus.route_id, env.now) * 60:
                        self.bunching += 1
                        self.route_stats[bus.route_id]["bunching"] += 1
                self.last_dep[key] = env.now
            if self.cfg.record:
                self.events.append({
                    "bus_id": bus.id, "trip_id": bus.trip_id, "route_id": bus.route_id,
                    "direction": direction, "stop_seq": i, "stop_id": stops[i],
                    "arr_s": round(now, 1), "dep_s": round(env.now, 1), "sched_s": round(sched, 1),
                    "boardings": round(boarded, 2), "alightings": round(float(alight), 2), "load": round(load, 2),
                })
            if i == n - 1:
                return
            seg = self.tt.seg_times_s(bus.route_id, direction, env.now / 60, self.speed_factor)[i]
            if self.noise_cv > 0:
                seg *= float(self.rng.lognormal(-0.5 * self.noise_cv ** 2, self.noise_cv))
            if env.now >= self.cfg.start_s:
                lf = load / self.net.capacity
                self.lf_time += lf * seg
                self.bus_time += seg
                if lf > 1.0:
                    self.overload_min += seg / 60
                    self.route_stats[bus.route_id]["overload_min"] += seg / 60
            yield env.timeout(seg)

    def _reassign(self, bus: Bus, direction: int):
        env = self.env
        kind, target = bus.reassign
        r = self.net.routes[bus.route_id]
        here = r.stops(direction)[-1]
        bus.reassign = None
        if kind == "release":
            bus.active = False
            depot = self.net.depots[r.depot_id]
            self.reserve[depot.id] = self.reserve.get(depot.id, 0) + 1
            return
        new = self.net.routes[target]
        best_dir = min((0, 1), key=lambda d: self.net.deadhead_km(here, new.terminal(d)))
        bus.route_id = target          # counts for the new route while it deadheads there
        bus.onboard = np.zeros(len(new.stop_ids))
        bus.last_load = 0.0
        yield env.timeout(self.net.deadhead_min(here, new.terminal(best_dir)) * 60)
        yield from self._run(bus, best_dir, env.now, fresh=True)

    def _spawn_reserve(self, depot_id: str, route_id: str):
        env = self.env
        depot = self.net.depots[depot_id]
        bus = self._new_bus(f"bus_DL1PR{self._next_reserve:02d}", route_id)
        self._next_reserve += 1
        r = self.net.routes[route_id]
        from ..core.network import haversine_km

        best_dir = min((0, 1), key=lambda d: haversine_km(depot.lat, depot.lon,
                                                          self.net.stops[r.terminal(d)].lat,
                                                          self.net.stops[r.terminal(d)].lon))
        s = self.net.stops[r.terminal(best_dir)]
        dh_min = 1.3 * haversine_km(depot.lat, depot.lon, s.lat, s.lon) / float(self.net.config["deadhead_speed_kmh"]) * 60
        yield env.timeout(dh_min * 60)
        yield from self._run(bus, best_dir, env.now, fresh=True)

    def apply_move(self, mv: Move) -> int:
        """Start a move now. Returns the number of buses actually moved."""
        done = 0
        if mv.from_route is None:
            depot_id = self.net.routes[mv.to_route].depot_id
            avail = self.reserve.get(depot_id, 0)
            for _ in range(min(mv.count, avail)):
                self.reserve[depot_id] -= 1
                self.env.process(self._spawn_reserve(depot_id, mv.to_route))
                done += 1
        else:
            cands = [b for b in self.buses if b.active and not b.broken and b.reassign is None
                     and b.route_id == mv.from_route]
            n_route = len(cands)
            cands.sort(key=lambda b: -b.stop_idx / max(1, len(b.onboard)))
            for b in cands[: min(mv.count, max(0, n_route - 1))]:
                b.reassign = ("release", None) if mv.to_route is None else ("move", mv.to_route)
                done += 1
        if done:
            self.changes += 1
            self.deadhead_km += mv.deadhead_km * done
            self.moves_done.append(Move(self.env.now, mv.from_route, mv.to_route, done, mv.deadhead_km))
        return done

    def _moves_proc(self):
        for mv in sorted(self.cfg.moves, key=lambda m: m.at_s):
            if mv.at_s > self.env.now:
                yield self.env.timeout(mv.at_s - self.env.now)
            self.apply_move(mv)

    def _planner_proc(self):
        t = self.cfg.start_s
        while t < self.cfg.end_s:
            if t > self.env.now:
                yield self.env.timeout(t - self.env.now)
            for mv in self.cfg.planner(self, self.env.now) or []:
                self.apply_move(mv)
            t += self.cfg.planner_every_s

    def _breakdown_proc(self, route_id: str, at_s: float):
        yield self.env.timeout(max(0.0, at_s - self.env.now))
        cands = [b for b in self.buses if b.active and not b.broken and b.route_id == route_id]
        if not cands:
            return
        bus = min(cands, key=lambda b: abs(b.stop_idx - len(b.onboard) / 2))
        bus.broken = True
        self.breakdown_log.append({"bus_id": bus.id, "route_id": route_id, "t_s": self.env.now})
        if self.env.now >= self.cfg.start_s:
            stranded = float(bus.onboard.sum())
            self.left_behind += stranded
            self.route_stats[route_id]["left_behind"] += stranded

    def _sampler(self):
        t = self.cfg.start_s
        while t <= self.cfg.end_s:
            if t > self.env.now:
                yield self.env.timeout(t - self.env.now)
            row = {"t_s": t}
            for rid in self.route_ids:
                loads = [b.last_load for b in self.buses if b.active and not b.broken and b.route_id == rid]
                row[rid] = round(max(loads), 3) if loads else 0.0
            self.series.append(row)
            t += self.cfg.sample_every_s

    # ---- run -------------------------------------------------------------------------
    def run(self) -> dict:
        self._place_initial()
        if self.cfg.moves:
            self.env.process(self._moves_proc())
        if self.cfg.planner is not None:
            self.env.process(self._planner_proc())
        for bd in self.cfg.breakdowns:
            if bd["route_id"] in self.route_ids:
                self.env.process(self._breakdown_proc(bd["route_id"], bd["at_s"]))
        self.env.process(self._sampler())
        self.env.run(until=self.cfg.end_s)
        # passengers still waiting at the end count with their censored wait
        for (rid, _, _), q in self.queues.items():
            for g in q["groups"]:
                t_mid = max(self.cfg.start_s, (g[0] + g[1]) / 2)
                if g[2] > 0 and t_mid < self.cfg.end_s:
                    w = self.cfg.end_s - t_mid
                    self.wait_s.append(w)
                    self.wait_n.append(g[2])
                    self.route_stats[rid]["wait_s"] += w * g[2]
                    self.route_stats[rid]["wait_n"] += g[2]
        return self.metrics()

    def metrics(self) -> dict:
        w = np.asarray(self.wait_s)
        n = np.asarray(self.wait_n)
        if n.sum() > 0:
            avg = float((w * n).sum() / n.sum())
            order = np.argsort(w)
            cum = np.cumsum(n[order]) / n.sum()
            p95 = float(w[order][min(len(w) - 1, int(np.searchsorted(cum, 0.95)))])
        else:
            avg = p95 = 0.0
        hours = max(1e-9, (self.cfg.end_s - self.cfg.start_s) / 3600)
        return {
            "avg_wait_min": round(avg / 60, 2),
            "p95_wait_min": round(p95 / 60, 2),
            "left_behind": int(round(self.left_behind)),
            "overload_min": int(round(self.overload_min)),
            "bunching_events": int(self.bunching),
            "avg_load_factor": round(float(self.lf_time / self.bus_time), 3) if self.bus_time else 0.0,
            "deadhead_km": round(self.deadhead_km, 1),
            "changes_per_hour": round(self.changes / hours, 2),
        }

    def route_metrics(self, route_id: str) -> dict:
        s = self.route_stats[route_id]
        return {
            "avg_wait_min": round(s["wait_s"] / s["wait_n"] / 60, 2) if s["wait_n"] else 0.0,
            "left_behind": int(round(s["left_behind"])),
            "overload_min": int(round(s["overload_min"])),
            "bunching_events": int(s["bunching"]),
        }
