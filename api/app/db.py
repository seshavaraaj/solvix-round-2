"""Database access (plan B3.1). SQLAlchemy Core tables; SQLite locally,
Render Postgres in the cloud. `api/schema.sql` is generated from these tables
(`python scripts/seed_db.py --print-schema`)."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import (Column, Float, Integer, MetaData, String, Table, Text, UniqueConstraint, create_engine,
                        insert, select, text, update)
from sqlalchemy.engine import Engine

from .config import settings

metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(64), nullable=False, unique=True),
    Column("password_hash", String(128), nullable=False),
    Column("role", String(16), nullable=False),
    Column("created_at", String(40), nullable=False),
)

recommendations = Table(
    "recommendations", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("scenario", String(40), nullable=False),
    Column("t_s", Float, nullable=False),               # replay time of the cycle
    Column("created_at", String(40), nullable=False),
    Column("action", String(16), nullable=False),
    Column("from_route_id", String(32)),
    Column("to_route_id", String(32)),
    Column("bus_count", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("payload", Text, nullable=False),            # full Recommendation JSON
)

decisions = Table(
    "decisions", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("recommendation_id", String(32), nullable=False),
    Column("decision", String(16), nullable=False),
    Column("reason", String(32)),
    Column("note", Text),
    Column("decided_by", String(64), nullable=False),
    Column("decided_at", String(40), nullable=False),        # replay time, same clock as created_at
    Column("decided_wall_at", String(40)),                   # real time, for the audit trail
    UniqueConstraint("recommendation_id", name="uq_decisions_recommendation"),
)

routes_config = Table(
    "routes_config", metadata,
    Column("route_id", String(32), primary_key=True),
    Column("payload", Text, nullable=False),            # Route JSON (contract §5)
    Column("updated_at", String(40), nullable=False),
)

fleet_config = Table(
    "fleet_config", metadata,
    Column("depot_id", String(32), primary_key=True),
    Column("name", String(80), nullable=False),
    Column("lat", Float, nullable=False),
    Column("lon", Float, nullable=False),
    Column("fleet_size", Integer, nullable=False),
    Column("reserve", Integer, nullable=False),
    Column("out_of_service", Integer, nullable=False),
    Column("updated_at", String(40), nullable=False),
)

crowding_reports = Table(
    "crowding_reports", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("device_id", String(64), nullable=False),
    Column("bus_id", String(40), nullable=False),
    Column("route_id", String(32), nullable=False),
    Column("level", String(16), nullable=False),
    Column("lat", Float),
    Column("lon", Float),
    Column("received_at", String(40), nullable=False),
    Column("received_ts", Float, nullable=False),
)

_engine: Engine | None = None


def engine() -> Engine:
    global _engine
    if _engine is None:
        url = settings.database_url
        kwargs: dict[str, Any] = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs.update(pool_size=3, max_overflow=2)   # small pool for Render free Postgres
        _engine = create_engine(url, **kwargs)
    return _engine


def reset_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def create_all() -> None:
    metadata.create_all(engine())


def ping() -> bool:
    try:
        with engine().connect() as c:
            c.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def rec_id(n: int) -> str:
    return f"rec_{n:04d}"


def rec_num(rec: str) -> int | None:
    try:
        return int(rec.split("_", 1)[1])
    except (IndexError, ValueError):
        return None


def load_json(s: str) -> Any:
    return json.loads(s)


__all__ = ["users", "recommendations", "decisions", "routes_config", "fleet_config", "crowding_reports",
           "engine", "create_all", "ping", "insert", "select", "update", "rec_id", "rec_num", "load_json"]
