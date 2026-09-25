"""POST /cycle, GET /recommendations (plan B4.5–B4.6)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool

from ..auth import require_role
from ..ops import list_recommendations, run_cycle
from ..schemas import CycleOut, Recommendation
from ..service import state

router = APIRouter(tags=["recommendations"])


@router.post("/cycle", response_model=CycleOut)
async def cycle(t: str | None = Query(default=None), _: dict = Depends(require_role("operator"))) -> dict:
    ts = state.parse_t(t)
    ran, recs = await run_in_threadpool(run_cycle, state, ts)
    return {"t": state.iso(ts), "ran": ran, "recommendations": recs}


@router.get("/recommendations", response_model=list[Recommendation])
def recommendations(status: Literal["pending", "approved", "rejected", "expired"] | None = None,
                    _: dict = Depends(require_role("operator"))) -> list[dict]:
    return list_recommendations(state, status=status)
