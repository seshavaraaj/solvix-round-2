"""Admin CRUD on routes_config / fleet_config (plan B6.5).

New routes are stored and served by /routes, but only routes present in the
replay network get buses, forecasts and recommendations. Edits to
min_headway_min and to depot fleet numbers feed the optimiser immediately.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import insert, select, update

from .. import db
from ..auth import require_role
from ..core.timeutil import now_iso
from ..errors import ApiError
from ..schemas import FleetConfig, Route
from ..service import state

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role("admin"))])


def _save_route(route: dict) -> None:
    with db.engine().begin() as c:
        exists = c.execute(select(db.routes_config.c.route_id)
                           .where(db.routes_config.c.route_id == route["id"])).first()
        values = {"payload": json.dumps(route), "updated_at": now_iso()}
        if exists:
            c.execute(update(db.routes_config).where(db.routes_config.c.route_id == route["id"]).values(**values))
        else:
            c.execute(insert(db.routes_config).values(route_id=route["id"], **values))


@router.get("/routes", response_model=list[Route])
def list_routes() -> list[dict]:
    return [state.routes_cfg[k] for k in sorted(state.routes_cfg)]


@router.post("/routes", response_model=Route, status_code=201)
def create_route(body: Route) -> dict:
    if body.id in state.routes_cfg:
        raise ApiError(409, "conflict", f"route {body.id} already exists")
    if body.depot_id not in state.fleet_cfg:
        raise ApiError(400, "bad_request", f"unknown depot {body.depot_id}")
    route = body.model_dump()
    _save_route(route)
    state.routes_cfg[body.id] = route
    return route


@router.put("/routes/{route_id}", response_model=Route)
def update_route(route_id: str, body: Route) -> dict:
    if route_id not in state.routes_cfg:
        raise ApiError(404, "not_found", f"route {route_id} not found")
    if body.id != route_id:
        raise ApiError(400, "bad_request", "id in body must match the path")
    if body.depot_id not in state.fleet_cfg:
        raise ApiError(400, "bad_request", f"unknown depot {body.depot_id}")
    route = body.model_dump()
    _save_route(route)
    state.routes_cfg[route_id] = route
    state.apply_admin_config()
    return route


@router.get("/fleet", response_model=list[FleetConfig])
def list_fleet() -> list[dict]:
    return [state.fleet_cfg[k] for k in sorted(state.fleet_cfg)]


@router.put("/fleet/{depot_id}", response_model=FleetConfig)
def update_fleet(depot_id: str, body: FleetConfig) -> dict:
    if depot_id not in state.fleet_cfg:
        raise ApiError(404, "not_found", f"depot {depot_id} not found")
    if body.depot_id != depot_id:
        raise ApiError(400, "bad_request", "depot_id in body must match the path")
    if body.reserve + body.out_of_service > body.fleet_size:
        raise ApiError(400, "bad_request", "reserve + out_of_service cannot exceed fleet_size")
    cfg = body.model_dump()
    with db.engine().begin() as c:
        exists = c.execute(select(db.fleet_config.c.depot_id).where(db.fleet_config.c.depot_id == depot_id)).first()
        values = {**cfg, "updated_at": now_iso()}
        if exists:
            c.execute(update(db.fleet_config).where(db.fleet_config.c.depot_id == depot_id).values(**values))
        else:
            c.execute(insert(db.fleet_config).values(**values))
    state.fleet_cfg[depot_id] = cfg
    state.apply_admin_config()
    return cfg
