"""POST /auth/login, POST /auth/device (contract §4)."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from .. import db
from ..auth import issue, verify_password
from ..errors import ApiError
from ..schemas import DeviceIn, LoginIn, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn) -> dict:
    with db.engine().connect() as c:
        row = c.execute(select(db.users).where(db.users.c.username == body.username)).mappings().first()
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise ApiError(401, "unauthorized", "wrong username or password")
    return issue(row["username"], row["role"])


@router.post("/device", response_model=TokenOut)
def device(body: DeviceIn) -> dict:
    return issue(body.device_id, "rider")
