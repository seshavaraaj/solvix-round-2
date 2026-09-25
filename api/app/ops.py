"""Recommendation cycle, decisions and what-if (plan B4, B5)."""
from __future__ import annotations

import json
import math
import time

import numpy as np
from sqlalchemy import insert, select, update

from . import db
from .core.explain import explain
from .core.optimise import BAND_MIN, MAX_CHANGES_PER_HOUR, N_BANDS, RouteInput, solve
from .core.planning import build_problem, expected_effect, route_inputs
from .core.timeutil import now_iso
from .errors import ApiError
from .service import AppState
from .sim.model import Move, SimConfig, Simulation

CYCLE_EVERY_S = 15 * 60
WHATIF_HORIZON_S = 120 * 60
WHATIF_SEEDS = (11, 12)


# ---- helpers -------------------------------------------------------------------------------
def _usable_reserve(st: AppState) -> dict[str, int]:
    """Depot reserve minus out-of-service minus reserve buses already sent out."""
    used: dict[str, int] = {}
    for m in st.replay.mods.get(st.scenario, []):
        if m.from_route is None and m.to_route:
            dep = st.net.routes[m.to_route].depot_id
            used[dep] = used.get(dep, 0) + m.count
        if m.to_route is None and m.from_route:
            dep = st.net.routes[m.from_route].depot_id
            used[dep] = used.get(dep, 0) - m.count
    return {d.id: max(0, d.reserve - d.out_of_service - used.get(d.id, 0)) for d in st.net.depots.values()}


def _moves_left(st: AppState, t: float) -> dict[str, int]:
    left = {rid: MAX_CHANGES_PER_HOUR for rid in st.net.routes}
    for m in st.replay.mods.get(st.scenario, []):
        if t - 3600 < m.t_s <= t:
            for r in (m.from_route, m.to_route):
                if r in left:
                    left[r] -= 1
    return left


def _duty_ok(st: AppState, t: float, states) -> dict[str, int]:
    """Buses whose driver's shift covers the whole window (simplified duty check)."""
    shift = st.replay.shift_end()
    end = t + N_BANDS * BAND_MIN * 60 + 1800          # window + time to reach the new route
    out = {rid: 0 for rid in st.net.routes}
    for s in states:
        if s.in_service and s.route_id in out and shift.get(s.id, 10 ** 9) >= end:
            out[s.route_id] += 1
    return out


def _rows_to_recs(rows) -> list[dict]:
    out = []
    for r in rows:
        rec = json.loads(r["payload"])
        rec["status"] = r["status"]
        out.append(rec)
    return out


# ---- cycle -----------------------------------------------------------------------------------
def run_cycle(st: AppState, t: float) -> tuple[bool, list[dict]]:
    scen = st.scenario
    cache = st.cycle_cache.get(scen)
    if cache and 0 <= t - cache["t_s"] < CYCLE_EVERY_S:
        return False, list_recommendations(st, ids=cache["ids"])

    states = st.visible_states(t)
    a = st.analyse(t, states)
    p = st.replay.scenario_params()
    fc, view = st.forecaster, a.view
    inputs = route_inputs(
        st.net, st.dm, st.tt, t, a.fleet,
        rate_p50=lambda r, d, m: fc.stop_rates(view, r, d, m, "p50"),
        rate_p90=lambda r, d, m: fc.stop_rates(view, r, d, m, "p90"),
        speed_factor=p["speed_factor"], duty_ok=_duty_ok(st, t, states), load_scale=a.crowd_scale,
    )
    recent = [(m.from_route, m.to_route) for m in st.replay.mods.get(scen, []) if t - 3600 < m.t_s <= t]
    problem = build_problem(st.net, inputs, _usable_reserve(st), _moves_left(st, t), recent)
    plan = solve(problem)
    by_route: dict[str, RouteInput] = {r.route_id: r for r in inputs}

    w_start = math.ceil(t / (BAND_MIN * 60)) * BAND_MIN * 60
    w_end = w_start + N_BANDS * BAND_MIN * 60
    created = st.iso(t)
    recs = []
    for act in plan.actions:
        to_in = by_route.get(act.to_route_id) if act.to_route_id else None
        fr_in = by_route.get(act.from_route_id) if act.from_route_id else None
        effect = {
            "to_route": expected_effect(to_in, to_in.n_buses + act.bus_count) if to_in else None,
            "from_route": expected_effect(fr_in, fr_in.n_buses - act.bus_count) if fr_in else None,
        }
        trig, confs, to_stop = [], [], None
        for rid, kinds in ((act.to_route_id, ("overcrowded", "bunching", "delay_emerging")),
                           (act.from_route_id, ("underused",))):
            if not rid:
                continue
            for d in (0, 1):
                for k in kinds:
                    f = a.flags[rid, d][k]
                    if f.on:
                        if k not in trig:
                            trig.append(k)
                        confs.append(f.confidence)
                        if k == "overcrowded" and to_stop is None:
                            to_stop = f.detail.get("stop")
        trig.sort(key=("overcrowded", "underused", "delay_emerging", "bunching").index)
        conf = min(confs, key=("low", "medium", "high").index) if confs else "medium"
        rec = {
            "id": "", "created_at": created, "action": act.action, "from_route_id": act.from_route_id,
            "to_route_id": act.to_route_id, "bus_count": int(act.bus_count),
            "window_start": st.iso(w_start), "window_end": st.iso(w_end), "trigger_flags": trig,
            "expected_effect": effect, "deadhead_km": round(float(act.deadhead_km), 1), "confidence": conf,
            "explanation": "", "status": "pending", "solver": plan.solver,
        }
        dep_route = act.to_route_id or act.from_route_id
        ctx = {"to_stop": to_stop, "depot_name": st.net.depots[st.net.routes[dep_route].depot_id].name,
               "from_min_headway": st.net.routes[act.from_route_id].min_headway_min if act.from_route_id else None}
        rec["explanation"] = explain(rec, ctx)
        recs.append(rec)

    with db.engine().begin() as c:
        c.execute(update(db.recommendations)
                  .where((db.recommendations.c.scenario == scen) & (db.recommendations.c.status == "pending"))
                  .values(status="expired"))
        ids = []
        for rec in recs:
            res = c.execute(insert(db.recommendations).values(
                scenario=scen, t_s=t, created_at=rec["created_at"], action=rec["action"],
                from_route_id=rec["from_route_id"], to_route_id=rec["to_route_id"], bus_count=rec["bus_count"],
                status="pending", payload="{}"))
            n = int(res.inserted_primary_key[0])
            rec["id"] = db.rec_id(n)
            c.execute(update(db.recommendations).where(db.recommendations.c.id == n)
                      .values(payload=json.dumps(rec)))
            ids.append(n)
    st.cycle_cache[scen] = {"t_s": t, "ids": ids, "solver": plan.solver, "status": plan.status,
                            "runtime_s": plan.runtime_s}
    return True, recs


def list_recommendations(st: AppState, status: str | None = None, ids: list[int] | None = None) -> list[dict]:
    q = select(db.recommendations).where(db.recommendations.c.scenario == st.scenario)
    if status:
        q = q.where(db.recommendations.c.status == status)
    if ids is not None:
        if not ids:
            return []
        q = q.where(db.recommendations.c.id.in_(ids))
    with db.engine().connect() as c:
        rows = c.execute(q.order_by(db.recommendations.c.id.desc())).mappings().all()
    return _rows_to_recs(rows)


def get_recommendation(st: AppState, rec: str) -> dict:
    n = db.rec_num(rec)
    if n is None:
        raise ApiError(404, "not_found", f"recommendation {rec} not found")
    with db.engine().connect() as c:
        row = c.execute(select(db.recommendations).where(db.recommendations.c.id == n)).mappings().first()
    if row is None:
        raise ApiError(404, "not_found", f"recommendation {rec} not found")
    return _rows_to_recs([row])[0]


# ---- decisions --------------------------------------------------------------------------------
def decide(st: AppState, body: dict, user: str) -> dict:
    if body["decision"] == "reject" and not body.get("reason"):
        raise ApiError(400, "bad_request", "reason is required when rejecting")
    rec = get_recommendation(st, body["recommendation_id"])
    if rec["status"] != "pending":
        raise ApiError(409, "conflict", f"recommendation already {rec['status']}")
    n = db.rec_num(rec["id"])
    decision = {"recommendation_id": rec["id"], "decision": body["decision"],
                "reason": body.get("reason"),
                "note": body.get("note"), "decided_by": user, "decided_at": st.iso(st.now_s())}
    new_status = "approved" if body["decision"] == "approve" else "rejected"
    rec["status"] = new_status
    with db.engine().begin() as c:
        res = c.execute(update(db.recommendations)
                        .where((db.recommendations.c.id == n) & (db.recommendations.c.status == "pending"))
                        .values(status=new_status, payload=json.dumps(rec)))
        if res.rowcount == 0:
            raise ApiError(409, "conflict", "recommendation already decided")
        c.execute(insert(db.decisions).values(**decision, decided_wall_at=now_iso()))
    if new_status == "approved":
        st.replay.apply(rec["id"], rec["action"], rec["from_route_id"], rec["to_route_id"], rec["bus_count"],
                        st.now_s(), st.scenario)
    return decision


def list_decisions(limit: int, offset: int) -> list[dict]:
    with db.engine().connect() as c:
        rows = c.execute(select(db.decisions).order_by(db.decisions.c.id.desc()).limit(limit).offset(offset))
        return [{k: r[k] for k in ("recommendation_id", "decision", "reason", "note", "decided_by", "decided_at")}
                for r in rows.mappings()]


def decisions_csv() -> str:
    import csv
    import io

    with db.engine().connect() as c:
        rows = c.execute(
            select(db.decisions, db.recommendations.c.action, db.recommendations.c.from_route_id,
                   db.recommendations.c.to_route_id, db.recommendations.c.bus_count, db.recommendations.c.scenario)
            .select_from(db.decisions.outerjoin(
                db.recommendations,
                db.recommendations.c.id == _rec_num_expr()))
            .order_by(db.decisions.c.id)).mappings().all()
    buf = io.StringIO()
    cols = ["recommendation_id", "decision", "reason", "note", "decided_by", "decided_at", "scenario", "action",
            "from_route_id", "to_route_id", "bus_count"]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k) for k in cols})
    return buf.getvalue()


def _rec_num_expr():
    from sqlalchemy import Integer, cast, func

    # "rec_0017" -> 17, portable across SQLite and Postgres
    return cast(func.substr(db.decisions.c.recommendation_id, 5), Integer)


# ---- what-if ------------------------------------------------------------------------------------
def whatif(st: AppState, rec_id: str) -> dict:
    rec = get_recommendation(st, rec_id)
    t = st.now_s()
    started = time.perf_counter()
    p = st.replay.scenario_params()
    fleet = st.replay.fleet(t)          # in-service buses only; broken buses do not count
    reserve = _usable_reserve(st)
    focus = rec["to_route_id"] or rec["from_route_id"]
    mv = Move(at_s=t, from_route=rec["from_route_id"], to_route=rec["to_route_id"], count=rec["bus_count"],
              deadhead_km=rec["deadhead_km"])
    runs = {"without": [], "with": []}
    series_w, series_wo = [], []
    for seed in WHATIF_SEEDS:
        for label, moves in (("without", []), ("with", [mv])):
            cfg = SimConfig(start_s=t, end_s=t + WHATIF_HORIZON_S, day_type=p["day_type"], rain_mm=p["rain_mm"],
                            events=p["events"], breakdowns=[b for b in p["breakdowns"] if b["at_s"] > t],
                            fleet=fleet, reserve=reserve, strategy="transitpulse", moves=moves, seed=seed,
                            warmup_s=1800, sample_every_s=900)
            sim = Simulation(st.net, st.dm, st.tt, cfg)
            runs[label].append(sim.run())
            (series_w if label == "with" else series_wo).append([row.get(focus, 0.0) for row in sim.series])
    keys = ("avg_wait_min", "p95_wait_min", "left_behind", "overload_min", "bunching_events")

    def avg(label: str) -> dict:
        out = {k: float(np.mean([r[k] for r in runs[label]])) for k in keys}
        for k in ("left_behind", "overload_min", "bunching_events"):
            out[k] = int(round(out[k]))
        out["avg_wait_min"] = round(out["avg_wait_min"], 1)
        out["p95_wait_min"] = round(out["p95_wait_min"], 1)
        return out

    wo = np.mean(np.array(series_wo), axis=0)
    w = np.mean(np.array(series_w), axis=0)
    series = [{"t": st.iso(t + i * 900), "load_without": round(float(a), 2), "load_with": round(float(b), 2)}
              for i, (a, b) in enumerate(zip(wo, w))]
    return {"recommendation_id": rec["id"], "horizon_min": WHATIF_HORIZON_S // 60,
            "runtime_s": round(time.perf_counter() - started, 2), "without": avg("without"), "with": avg("with"),
            "series": series}
