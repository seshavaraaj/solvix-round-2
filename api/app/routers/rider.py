"""POST /crowding — rider crowding reports (plan B6.2)."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from sqlalchemy import insert, select

from .. import db
from ..auth import require_role
from ..core.crowding import RATE_LIMIT_S, Report
from ..core.timeutil import now_iso
from ..errors import ApiError
from ..schemas import CrowdingReport
from ..service import state

router = APIRouter(tags=["rider"])


@router.post("/crowding", status_code=201)
def crowding(body: CrowdingReport, user: dict = Depends(require_role("rider"))) -> dict:
    if body.route_id not in state.net.routes:
        raise ApiError(404, "not_found", f"route {body.route_id} not found")
    device = user["sub"]
    now = time.time()
    if not state.crowding.allowed(device, body.bus_id, now):
        raise ApiError(429, "rate_limited", "one report per bus every 5 minutes")
    with db.engine().begin() as c:
        recent = c.execute(select(db.crowding_reports.c.id)
                           .where((db.crowding_reports.c.device_id == device)
                                  & (db.crowding_reports.c.bus_id == body.bus_id)
                                  & (db.crowding_reports.c.received_ts > now - RATE_LIMIT_S))).first()
        if recent is not None:
            raise ApiError(429, "rate_limited", "one report per bus every 5 minutes")
        c.execute(insert(db.crowding_reports).values(
            device_id=device, bus_id=body.bus_id, route_id=body.route_id, level=body.level, lat=body.lat,
            lon=body.lon, received_at=now_iso(), received_ts=now))
    state.crowding.add(Report(device, body.bus_id, body.route_id, body.level, now))
    return {"accepted": True}
