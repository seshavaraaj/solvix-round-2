"""GET /state — buses, route health and feed health at replay time t."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth import require_role
from ..schemas import StateOut
from ..service import state

router = APIRouter(tags=["state"])


@router.get("/state", response_model=StateOut)
def get_state(t: str | None = Query(default=None), _: dict = Depends(require_role("operator"))) -> dict:
    ts = state.parse_t(t)
    states = state.visible_states(ts)
    analysis = state.analyse(ts, states)
    return {"t": state.iso(ts), "buses": [state.bus_json(s) for s in states], "route_health": analysis.health,
            "feed": state.feed(states)}
