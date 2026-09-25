"""GET/POST /clock — the in-memory replay clock (plan B3.4)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import update

from .. import db
from ..auth import require_role
from ..errors import ApiError
from ..schemas import ClockIn, ClockOut
from ..service import state

router = APIRouter(tags=["clock"])


def clock_json() -> dict:
    c = state.replay.clock
    return {"t": state.iso(c.now()), "speed": c.speed, "playing": c.playing, "scenario": c.scenario}


@router.get("/clock", response_model=ClockOut)
def get_clock(_: dict = Depends(require_role("operator"))) -> dict:
    return clock_json()


@router.post("/clock", response_model=ClockOut)
def post_clock(body: ClockIn, _: dict = Depends(require_role("operator"))) -> dict:
    rp = state.replay
    if body.action == "play":
        rp.clock.set(playing=True, speed=body.speed)
    elif body.action == "pause":
        rp.clock.set(playing=False, speed=body.speed)
    else:  # jump
        scenario = body.scenario or rp.clock.scenario
        if scenario not in rp.days:
            raise ApiError(400, "bad_request", f"unknown scenario {scenario}; one of {sorted(rp.days)}")
        day = rp.days[scenario]
        fresh_start = body.scenario is not None or body.t is None
        if fresh_start:
            # a scenario (re)start is a fresh demo run: undo fleet changes, expire open cards
            rp.reset(scenario)
            state.cycle_cache.pop(scenario, None)
            try:
                with db.engine().begin() as c:
                    c.execute(update(db.recommendations).where(db.recommendations.c.status == "pending")
                              .values(status="expired"))
            except Exception:
                pass
        rp.clock.set(scenario=scenario, window=day.window, playing=False, speed=body.speed)
        t = state.parse_t(body.t) if body.t else day.meta["clock_start_s"]
        rp.clock.set(t=t)
    return clock_json()
