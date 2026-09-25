"""Create tables and seed demo data (plan B3.2).

- operator / admin users with passwords from OPERATOR_PASSWORD / ADMIN_PASSWORD
  (never stored in Git; set them in .env locally or in the Render dashboard);
- routes_config and fleet_config from the GTFS subset in data/artefacts.

Idempotent: existing users get their password reset from the env; existing
config rows are kept unless --reset-config is given.

Run:  python scripts/seed_db.py [--reset-config]
      python scripts/seed_db.py --print-schema   # regenerate api/schema.sql
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "api"))

from sqlalchemy import delete, insert, select, update  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateTable  # noqa: E402

from app import db  # noqa: E402
from app.auth import hash_password  # noqa: E402
from app.config import settings  # noqa: E402
from app.core.network import load_network  # noqa: E402
from app.core.timeutil import now_iso  # noqa: E402


def print_schema() -> None:
    parts = ["-- Generated from api/app/db.py by `python scripts/seed_db.py --print-schema`.",
             "-- Postgres dialect. The app creates the same tables on SQLite with metadata.create_all().", ""]
    for table in db.metadata.sorted_tables:
        parts.append(str(CreateTable(table).compile(dialect=postgresql.dialect())).strip() + ";\n")
    (REPO / "api" / "schema.sql").write_text("\n".join(parts), encoding="utf-8")
    print("wrote api/schema.sql")


def seed(reset_config: bool) -> None:
    db.create_all()
    net = load_network(settings.artefacts_dir)
    now = now_iso()
    with db.engine().begin() as c:
        for username, role, pw in (("operator", "operator", settings.operator_password),
                                   ("admin", "admin", settings.admin_password)):
            if not pw:
                print(f"skip user {username}: set {role.upper()}_PASSWORD")
                continue
            row = c.execute(select(db.users.c.id).where(db.users.c.username == username)).first()
            if row:
                c.execute(update(db.users).where(db.users.c.id == row[0]).values(password_hash=hash_password(pw),
                                                                                 role=role))
            else:
                c.execute(insert(db.users).values(username=username, password_hash=hash_password(pw), role=role,
                                                  created_at=now))
            print(f"user {username} ({role}) ready")
        if reset_config:
            c.execute(delete(db.routes_config))
            c.execute(delete(db.fleet_config))
        have_routes = {r[0] for r in c.execute(select(db.routes_config.c.route_id))}
        for rid, r in net.routes.items():
            if rid in have_routes:
                continue
            payload = {
                "id": r.id, "name": r.name, "depot_id": r.depot_id, "color": r.color,
                "min_headway_min": r.min_headway_min, "shape": r.geojson(),
                "stops": [{"id": s, "name": net.stops[s].name, "lat": net.stops[s].lat, "lon": net.stops[s].lon,
                           "seq": i} for i, s in enumerate(r.stop_ids)],
            }
            c.execute(insert(db.routes_config).values(route_id=rid, payload=json.dumps(payload), updated_at=now))
        have_depots = {r[0] for r in c.execute(select(db.fleet_config.c.depot_id))}
        for d in net.depots.values():
            if d.id not in have_depots:
                c.execute(insert(db.fleet_config).values(
                    depot_id=d.id, name=d.name, lat=d.lat, lon=d.lon, fleet_size=d.fleet_size, reserve=d.reserve,
                    out_of_service=d.out_of_service, updated_at=now))
    print(f"seeded {len(net.routes)} routes, {len(net.depots)} depots into {settings.database_url.split('@')[-1]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print-schema", action="store_true")
    ap.add_argument("--reset-config", action="store_true")
    args = ap.parse_args()
    if args.print_schema:
        print_schema()
    else:
        seed(args.reset_config)


if __name__ == "__main__":
    main()
