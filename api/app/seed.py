"""Create tables and seed demo data (plan B3.2).

- operator / admin users with passwords from OPERATOR_PASSWORD / ADMIN_PASSWORD
  (never stored in Git; set them in .env locally or in the Render dashboard);
- routes_config and fleet_config from the GTFS subset in data/artefacts.

Idempotent: existing users get their password reset from the env; existing
config rows are kept unless reset_config is set; rows for routes or depots no
longer in the artefacts are removed. The API runs this in its
start-up thread, so the Render start command does not need a separate
`python scripts/seed_db.py` process.
"""
from __future__ import annotations

import json

from sqlalchemy import delete, insert, select, update

from . import db
from .auth import hash_password
from .config import settings
from .core.network import Network, load_network
from .core.timeutil import now_iso


def seed(reset_config: bool = False, net: Network | None = None) -> None:
    db.create_all()
    net = net or load_network(settings.artefacts_dir)
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
        # Drop config for routes / depots that are no longer in the artefacts (e.g. after a network rebuild).
        c.execute(delete(db.routes_config).where(db.routes_config.c.route_id.not_in(list(net.routes))))
        c.execute(delete(db.fleet_config).where(db.fleet_config.c.depot_id.not_in(list(net.depots))))
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
