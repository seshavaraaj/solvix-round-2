"""POST/GET /decisions, GET /decisions.csv (plan B4.6)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from ..auth import require_role
from ..ops import decide, decisions_csv, list_decisions
from ..schemas import Decision, DecisionIn
from ..service import state

router = APIRouter(tags=["decisions"])


@router.post("/decisions", response_model=Decision, status_code=201)
def post_decision(body: DecisionIn, user: dict = Depends(require_role("operator"))) -> dict:
    return decide(state, body.model_dump(), user["sub"])


@router.get("/decisions", response_model=list[Decision])
def get_decisions(limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0),
                  _: dict = Depends(require_role("operator", "admin"))) -> list[dict]:
    return list_decisions(limit, offset)


@router.get("/decisions.csv")
def get_decisions_csv(_: dict = Depends(require_role("operator", "admin"))) -> Response:
    return Response(decisions_csv(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="decisions.csv"'})
