"""Public rider-facing endpoints: /routes, /buses, /eta, /alerts, /results."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..errors import ApiError
from ..schemas import Alert, Bus, EtaOut, Route, ScenarioResult
from ..service import state

router = APIRouter(tags=["public"])


@router.get("/routes", response_model=list[Route])
def routes() -> list[dict]:
    return [state.routes_cfg[k] for k in sorted(state.routes_cfg)]


@router.get("/buses", response_model=list[Bus])
def buses(route_id: str | None = None, t: str | None = Query(default=None)) -> list[dict]:
    ts = state.parse_t(t)
    return [state.bus_json(s) for s in state.visible_states(ts)
            if s.in_service and (route_id is None or s.route_id == route_id)]


@router.get("/eta", response_model=list[EtaOut])
def eta(stop_id: str, route_id: str | None = None) -> list[dict]:
    if stop_id not in state.net.stops:
        raise ApiError(404, "not_found", f"stop {stop_id} not found")
    return state.eta(stop_id, route_id)


@router.get("/alerts", response_model=list[Alert])
def alerts(route_id: str | None = None) -> list[dict]:
    return state.alerts(route_id)


@router.get("/results", response_model=ScenarioResult)
def results() -> dict:
    if state.results is None:
        raise ApiError(404, "not_found", "results.json not built yet (run offline/sim/run_batch.py)")
    return state.results
