"""Mock API for frontend work before each milestone lands (contract §7).

Serves mock/fixtures/*.json on the real paths, accepts any login, fakes a
3-second /whatif, and moves buses along their route shapes as the clock `t`
advances so the map animates. Needs only FastAPI + Uvicorn.

Run from the repo root:  uvicorn mock.server:app --port 8000
Regenerate fixtures:     python mock/make_fixtures.py
"""
from __future__ import annotations

import asyncio
import copy
import json
import math
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

FIX = Path(__file__).resolve().parent / "fixtures"
SPEED_KMH = 18.0


def fx(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


app = FastAPI(title="AduthaBus Lite mock API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Content-Disposition"])

ROUTES = {r["id"]: r for r in fx("routes.json")}
BASE_STATE = fx("state.json")
T0 = datetime.fromisoformat(BASE_STATE["t"])


class Clock:
    def __init__(self) -> None:
        c = fx("clock.json")
        self.scenario = c["scenario"]
        self.speed = c["speed"]
        self.playing = False
        self.t = datetime.fromisoformat(c["t"])
        self.anchor = time.monotonic()

    def now(self) -> datetime:
        if self.playing:
            return self.t + timedelta(seconds=(time.monotonic() - self.anchor) * self.speed)
        return self.t

    def set(self, playing=None, speed=None, t=None, scenario=None) -> None:
        self.t, self.anchor = self.now(), time.monotonic()
        if t is not None:
            self.t = t
        if speed is not None:
            self.speed = speed
        if playing is not None:
            self.playing = playing
        if scenario is not None:
            self.scenario = scenario

    def json(self) -> dict:
        return {"t": self.now().isoformat(), "speed": self.speed, "playing": self.playing, "scenario": self.scenario}


clock = Clock()
decided: dict[str, dict] = {}
reports: dict[tuple[str, str], float] = {}
admin_routes = {r["id"]: r for r in fx("admin_routes.json")}
admin_fleet = {d["depot_id"]: d for d in fx("admin_fleet.json")}


def _shape_km(coords: list[list[float]]) -> list[float]:
    out = [0.0]
    for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
        dx = (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
        dy = (lat2 - lat1) * 110.57
        out.append(out[-1] + math.hypot(dx, dy))
    return out


def _project(coords: list[list[float]], km: list[float], lat: float, lon: float) -> float:
    best, best_d = 0.0, 1e9
    for i, (lo, la) in enumerate(coords):
        d = (lo - lon) ** 2 + (la - lat) ** 2
        if d < best_d:
            best, best_d = km[i], d
    return best


def _point(coords: list[list[float]], km: list[float], at: float) -> tuple[float, float, float]:
    at = max(0.0, min(at, km[-1]))
    for i in range(len(km) - 1):
        if km[i] <= at <= km[i + 1]:
            f = 0 if km[i + 1] == km[i] else (at - km[i]) / (km[i + 1] - km[i])
            (lo1, la1), (lo2, la2) = coords[i], coords[i + 1]
            brg = (math.degrees(math.atan2(lo2 - lo1, la2 - la1)) + 360) % 360
            return la1 + f * (la2 - la1), lo1 + f * (lo2 - lo1), round(brg)
    lo, la = coords[-1]
    return la, lo, 0


SHAPES = {rid: (r["shape"]["coordinates"], _shape_km(r["shape"]["coordinates"])) for rid, r in ROUTES.items()}


def moved_buses(now: datetime) -> list[dict]:
    """Fixture buses advanced along their shapes; they bounce at the terminals."""
    dt_h = (now - T0).total_seconds() / 3600
    out = []
    for b in copy.deepcopy(BASE_STATE["buses"]):
        coords, km = SHAPES[b["route_id"]]
        length = km[-1]
        start = _project(coords, km, b["lat"], b["lon"])
        pos0 = start if b["direction"] == 0 else 2 * length - start
        pos = (pos0 + (0 if b["dark"] else dt_h * SPEED_KMH)) % (2 * length)
        direction, along = (0, pos) if pos <= length else (1, 2 * length - pos)
        lat, lon, brg = _point(coords, km, along)
        b.update(lat=round(lat, 6), lon=round(lon, 6), direction=direction,
                 bearing=float(brg if direction == 0 else (brg + 180) % 360))
        if not b["dark"]:
            b["last_seen"] = now.isoformat()
        out.append(b)
    return out


def _auth(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    return h.split(" ", 1)[1] if h.lower().startswith("bearer ") else None


def _role(request: Request) -> str | None:
    tok = _auth(request)
    if tok is None:
        return None
    return "rider" if tok.startswith("mock-rider") else "admin" if tok.startswith("mock-admin") else "operator"


def need(request: Request, *roles: str) -> JSONResponse | None:
    role = _role(request)
    if role is None:
        return err(401, "unauthorized", "missing bearer token")
    if role not in roles:
        return err(403, "forbidden", f"requires role: {', '.join(roles)}")
    return None


@app.get("/health")
def health():
    return fx("health.json")


@app.post("/auth/login")
async def login(request: Request):
    body = await request.json()
    role = "admin" if body.get("username") == "admin" else "operator"
    return {**fx("auth_login.json"), "role": role, "token": f"mock-{role}-token"}


@app.post("/auth/device")
def device():
    return fx("auth_device.json")


@app.get("/clock")
def get_clock(request: Request):
    return need(request, "operator") or clock.json()


@app.post("/clock")
async def post_clock(request: Request):
    if (e := need(request, "operator")):
        return e
    body = await request.json()
    action = body.get("action")
    if action == "play":
        clock.set(playing=True, speed=body.get("speed"))
    elif action == "pause":
        clock.set(playing=False, speed=body.get("speed"))
    elif action == "jump":
        t = datetime.fromisoformat(body["t"]) if body.get("t") else T0
        clock.set(playing=False, t=t, speed=body.get("speed"), scenario=body.get("scenario"))
    else:
        return err(400, "bad_request", "action must be play, pause or jump")
    return clock.json()


@app.get("/state")
def state(request: Request, t: str | None = None):
    if (e := need(request, "operator")):
        return e
    now = datetime.fromisoformat(t) if t else clock.now()
    return {**BASE_STATE, "t": now.isoformat(), "buses": moved_buses(now)}


@app.get("/routes")
def routes():
    return list(ROUTES.values())


@app.get("/buses")
def buses(route_id: str | None = None, t: str | None = None):
    now = datetime.fromisoformat(t) if t else clock.now()
    return [b for b in moved_buses(now) if route_id is None or b["route_id"] == route_id]


@app.get("/eta")
def eta(stop_id: str, route_id: str | None = None):
    return [e for e in fx("eta.json") if route_id is None or e["route_id"] == route_id]


def _recs() -> list[dict]:
    out = []
    for r in fx("cycle.json")["recommendations"]:
        if r["id"] in decided:
            r["status"] = "approved" if decided[r["id"]]["decision"] == "approve" else "rejected"
        out.append(r)
    return out


@app.post("/cycle")
def cycle(request: Request, t: str | None = None):
    if (e := need(request, "operator")):
        return e
    return {"t": (t or clock.now().isoformat()), "ran": True, "recommendations": _recs()}


@app.get("/recommendations")
def recommendations(request: Request, status: str | None = None):
    if (e := need(request, "operator")):
        return e
    return [r for r in _recs() if status is None or r["status"] == status]


@app.post("/decisions")
async def post_decision(request: Request):
    if (e := need(request, "operator")):
        return e
    body = await request.json()
    rid = body.get("recommendation_id")
    if rid in decided:
        return err(409, "conflict", "recommendation already decided")
    if body.get("decision") == "reject" and not body.get("reason"):
        return err(400, "bad_request", "reason is required when rejecting")
    d = {"recommendation_id": rid, "decision": body.get("decision"), "reason": body.get("reason"),
         "note": body.get("note"), "decided_by": "operator", "decided_at": clock.now().isoformat()}
    decided[rid] = d
    return JSONResponse(d, status_code=201)


@app.get("/decisions")
def decisions(request: Request, limit: int = 100, offset: int = 0):
    if (e := need(request, "operator", "admin")):
        return e
    return (list(decided.values())[::-1] + fx("decisions.json"))[offset:offset + limit]


@app.get("/decisions.csv")
def decisions_csv(request: Request):
    if (e := need(request, "operator", "admin")):
        return e
    return Response((FIX / "decisions.csv").read_text(encoding="utf-8"), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="decisions.csv"'})


@app.post("/whatif")
async def whatif(request: Request):
    if (e := need(request, "operator")):
        return e
    body = await request.json()
    await asyncio.sleep(3)
    return {**fx("whatif.json"), "recommendation_id": body.get("recommendation_id", "rec_0001")}


@app.get("/results")
def results():
    return fx("results.json")


@app.get("/alerts")
def alerts(route_id: str | None = None):
    return [a for a in fx("alerts.json") if route_id is None or a["route_id"] == route_id]


@app.post("/crowding")
async def crowding(request: Request):
    if (e := need(request, "rider")):
        return e
    body = await request.json()
    key = (_auth(request), body.get("bus_id"))
    if time.time() - reports.get(key, 0) < 300:
        return err(429, "rate_limited", "one report per bus every 5 minutes")
    reports[key] = time.time()
    return JSONResponse({"accepted": True}, status_code=201)


@app.get("/admin/routes")
def admin_list_routes(request: Request):
    return need(request, "admin") or list(admin_routes.values())


@app.post("/admin/routes")
async def admin_create_route(request: Request):
    if (e := need(request, "admin")):
        return e
    body = await request.json()
    if body.get("id") in admin_routes:
        return err(409, "conflict", "route already exists")
    admin_routes[body["id"]] = body
    return JSONResponse(body, status_code=201)


@app.put("/admin/routes/{route_id}")
async def admin_update_route(route_id: str, request: Request):
    if (e := need(request, "admin")):
        return e
    if route_id not in admin_routes:
        return err(404, "not_found", "route not found")
    admin_routes[route_id] = await request.json()
    return admin_routes[route_id]


@app.get("/admin/fleet")
def admin_list_fleet(request: Request):
    return need(request, "admin") or list(admin_fleet.values())


@app.put("/admin/fleet/{depot_id}")
async def admin_update_fleet(depot_id: str, request: Request):
    if (e := need(request, "admin")):
        return e
    if depot_id not in admin_fleet:
        return err(404, "not_found", "depot not found")
    admin_fleet[depot_id] = await request.json()
    return admin_fleet[depot_id]
