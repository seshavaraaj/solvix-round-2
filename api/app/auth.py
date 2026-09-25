"""Self-rolled JWT auth (contract §4). bcrypt for password hashes, PyJWT for tokens."""
from __future__ import annotations

import time
from datetime import datetime

import bcrypt
import jwt
from fastapi import Depends, Request

from .config import settings
from .core.timeutil import IST
from .errors import ApiError

ALGO = "HS256"
LIFETIME_S = {"operator": 12 * 3600, "admin": 12 * 3600, "rider": 30 * 24 * 3600}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


def issue(sub: str, role: str) -> dict:
    exp = int(time.time()) + LIFETIME_S[role]
    token = jwt.encode({"sub": sub, "role": role, "exp": exp}, settings.jwt_secret, algorithm=ALGO)
    return {"token": token, "role": role, "expires_at": datetime.fromtimestamp(exp, IST).isoformat()}


def decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGO])
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(401, "unauthorized", "token expired") from exc
    except jwt.PyJWTError as exc:
        raise ApiError(401, "unauthorized", "invalid token") from exc


def claims(request: Request) -> dict:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise ApiError(401, "unauthorized", "missing bearer token")
    return decode(header.split(" ", 1)[1].strip())


def require_role(*roles: str):
    def dep(c: dict = Depends(claims)) -> dict:
        if c.get("role") not in roles:
            raise ApiError(403, "forbidden", f"requires role: {', '.join(roles)}")
        return c

    return dep
