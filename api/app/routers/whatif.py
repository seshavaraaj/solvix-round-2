"""POST /whatif — 2-hour simulation with vs without a recommendation (plan B5.6)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from ..auth import require_role
from ..ops import whatif
from ..schemas import WhatIfIn, WhatIfResult
from ..service import state

router = APIRouter(tags=["whatif"])


@router.post("/whatif", response_model=WhatIfResult, response_model_by_alias=True)
async def post_whatif(body: WhatIfIn, _: dict = Depends(require_role("operator"))) -> dict:
    return await run_in_threadpool(whatif, state, body.recommendation_id)
