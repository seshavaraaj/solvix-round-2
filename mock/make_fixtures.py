"""Regenerate mock/fixtures/*.json from the real API (plan B0.2, contract §7).

Runs the API in-process on the event-surge scenario at 17:15, calls every
endpoint in contract §6 and saves each response, so fixtures always match
the real shapes. Uses a throw-away SQLite database.

Run: python mock/make_fixtures.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "mock" / "fixtures"
tmp = Path(tempfile.mkdtemp()) / "fixtures.db"
os.environ["DATABASE_URL"] = f"sqlite:///{tmp.as_posix()}"
os.environ["OPERATOR_PASSWORD"] = "fixture"
os.environ["ADMIN_PASSWORD"] = "fixture"
os.environ.setdefault("JWT_SECRET", "fixture-secret-0123456789abcdef0123456789")
sys.path.insert(0, str(REPO / "api"))
sys.path.insert(0, str(REPO / "scripts"))
warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient  # noqa: E402

import seed_db  # noqa: E402
from app.main import app  # noqa: E402

T0 = "2026-09-25T17:15:00+05:30"


def save(name: str, data) -> None:
    path = FIXTURES / name
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  {name}")


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    seed_db.seed(reset_config=True)
    with TestClient(app) as c:
        while c.get("/health").json()["status"] != "ok":
            time.sleep(0.2)
        save("health.json", c.get("/health").json())
        login = c.post("/auth/login", json={"username": "operator", "password": "fixture"}).json()
        save("auth_login.json", {**login, "token": "mock-operator-token"})
        op = {"Authorization": f"Bearer {login['token']}"}
        admin_tok = c.post("/auth/login", json={"username": "admin", "password": "fixture"}).json()["token"]
        ad = {"Authorization": f"Bearer {admin_tok}"}
        dev = c.post("/auth/device", json={"device_id": "3f2b8c1e-mock-device"}).json()
        save("auth_device.json", {**dev, "token": "mock-rider-token"})
        rider = {"Authorization": f"Bearer {dev['token']}"}

        save("clock.json", c.post("/clock", json={"action": "jump", "scenario": "event_surge", "t": T0},
                                  headers=op).json())
        save("state.json", c.get("/state", headers=op).json())
        save("routes.json", c.get("/routes").json())
        save("buses.json", c.get("/buses").json())
        save("eta.json", c.get("/eta", params={"stop_id": "stop_1021"}).json())
        cyc = c.post("/cycle", headers=op).json()
        save("cycle.json", cyc)
        recs = cyc["recommendations"]
        save("recommendations.json", c.get("/recommendations", headers=op).json())
        if recs:
            save("whatif.json", c.post("/whatif", json={"recommendation_id": recs[0]["id"]}, headers=op).json())
            dec = c.post("/decisions", json={"recommendation_id": recs[0]["id"], "decision": "approve"},
                         headers=op).json()
            save("decisions_post.json", dec)
        for r in recs[1:2]:
            c.post("/decisions", json={"recommendation_id": r["id"], "decision": "reject", "reason": "no_driver",
                                       "note": "Driver shift ends 18:00"}, headers=op)
        save("decisions.json", c.get("/decisions", headers=ad).json())
        save("decisions.csv", c.get("/decisions.csv", headers=ad).text)
        save("results.json", c.get("/results").json())
        bus = c.get("/buses", params={"route_id": "534"}).json()[0]
        save("crowding.json", c.post("/crowding", json={"bus_id": bus["id"], "route_id": "534", "level": "crowded",
                                                          "lat": bus["lat"], "lon": bus["lon"]}, headers=rider).json())
        save("alerts.json", c.get("/alerts").json())
        save("admin_routes.json", c.get("/admin/routes", headers=ad).json())
        save("admin_fleet.json", c.get("/admin/fleet", headers=ad).json())


if __name__ == "__main__":
    main()
