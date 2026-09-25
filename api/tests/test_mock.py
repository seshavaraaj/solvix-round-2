"""Mock server (contract §7): serves fixtures, any login works, buses move."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture(scope="module")
def mock():
    from fastapi.testclient import TestClient

    from mock.server import app

    with TestClient(app) as c:
        yield c


def test_mock_login_and_state_moves(mock):
    tok = mock.post("/auth/login", json={"username": "anyone", "password": "x"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    s1 = mock.get("/state", params={"t": "2026-09-25T17:15:00+05:30"}, headers=h).json()
    s2 = mock.get("/state", params={"t": "2026-09-25T17:25:00+05:30"}, headers=h).json()
    moved = [a["id"] for a, b in zip(s1["buses"], s2["buses"]) if (a["lat"], a["lon"]) != (b["lat"], b["lon"])]
    assert len(moved) > len(s1["buses"]) // 2
    assert set(s1) == {"t", "buses", "route_health", "feed"}


def test_mock_decisions_and_errors(mock):
    h = {"Authorization": "Bearer mock-operator-token"}
    rid = mock.post("/cycle", headers=h).json()["recommendations"][0]["id"]
    assert mock.post("/decisions", json={"recommendation_id": rid, "decision": "approve"}, headers=h).status_code == 201
    assert mock.post("/decisions", json={"recommendation_id": rid, "decision": "approve"}, headers=h).status_code == 409
    assert mock.get("/state").status_code == 401
    assert mock.get("/admin/fleet", headers=h).status_code == 403
    assert mock.get("/admin/fleet", headers={"Authorization": "Bearer mock-admin-token"}).status_code == 200
