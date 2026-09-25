"""Contract test (plan B3.8): every endpoint's real response has the same
keys and value types as its fixture in mock/fixtures/ (contract §7 rule)."""
import json
from pathlib import Path

import pytest

FIX = Path(__file__).resolve().parents[2] / "mock" / "fixtures"


def kind(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    return type(v).__name__


def same_shape(real, fix, path="$"):
    if real is None or fix is None:
        return  # nullable field: shape cannot be compared
    assert kind(real) == kind(fix), f"{path}: {kind(real)} != {kind(fix)}"
    if isinstance(real, dict):
        assert set(real) == set(fix), f"{path}: keys {sorted(set(real) ^ set(fix))} differ"
        for k in real:
            same_shape(real[k], fix[k], f"{path}.{k}")
    elif isinstance(real, list) and real and fix:
        if all(isinstance(x, dict) for x in fix):
            for i, item in enumerate(real):
                same_shape(item, fix[min(i, len(fix) - 1)], f"{path}[{i}]")
        else:  # scalar lists, e.g. error_levels [0, 0.2, 0.4, "missed_surge"]
            assert {kind(x) for x in real} <= {kind(x) for x in fix} | {None}, path


@pytest.fixture(scope="module")
def surge(client, op):
    r = client.post("/clock", json={"action": "jump", "scenario": "event_surge",
                                    "t": "2026-09-25T17:15:00+05:30"}, headers=op)
    assert r.status_code == 200
    cyc = client.post("/cycle", headers=op)
    assert cyc.status_code == 200
    return cyc.json()


def fixture(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("method,path,params,body,auth,fix", [
    ("get", "/health", None, None, None, "health.json"),
    ("get", "/clock", None, None, "op", "clock.json"),
    ("get", "/state", None, None, "op", "state.json"),
    ("get", "/routes", None, None, None, "routes.json"),
    ("get", "/buses", None, None, None, "buses.json"),
    ("get", "/eta", {"stop_id": "1465"}, None, None, "eta.json"),
    ("get", "/recommendations", None, None, "op", "recommendations.json"),
    ("get", "/results", None, None, None, "results.json"),
    ("get", "/alerts", None, None, None, "alerts.json"),
    ("get", "/admin/routes", None, None, "admin", "admin_routes.json"),
    ("get", "/admin/fleet", None, None, "admin", "admin_fleet.json"),
])
def test_get_endpoints_match_fixtures(client, op, admin, surge, method, path, params, body, auth, fix):
    headers = {"op": op, "admin": admin}.get(auth)
    r = client.request(method.upper(), path, params=params, json=body, headers=headers)
    assert r.status_code == 200, r.text
    same_shape(r.json(), fixture(fix))


def test_auth_endpoints_match_fixtures(client):
    same_shape(client.post("/auth/login", json={"username": "operator", "password": "op-test"}).json(),
               fixture("auth_login.json"))
    same_shape(client.post("/auth/device", json={"device_id": "contract-device-1"}).json(),
               fixture("auth_device.json"))


def test_cycle_whatif_decisions_match_fixtures(client, op, admin, surge):
    same_shape(surge, fixture("cycle.json"))
    recs = surge["recommendations"]
    assert recs, "event surge at 17:15 must produce at least one card"
    w = client.post("/whatif", json={"recommendation_id": recs[0]["id"]}, headers=op)
    assert w.status_code == 200
    same_shape(w.json(), fixture("whatif.json"))
    d = client.post("/decisions", json={"recommendation_id": recs[0]["id"], "decision": "approve"}, headers=op)
    assert d.status_code == 201
    same_shape(d.json(), fixture("decisions_post.json"))
    same_shape(client.get("/decisions", headers=admin).json(), fixture("decisions.json"))
    csv = client.get("/decisions.csv", headers=admin)
    assert csv.headers["content-type"].startswith("text/csv")
    assert csv.text.splitlines()[0] == (FIX / "decisions.csv").read_text(encoding="utf-8").splitlines()[0]


def test_crowding_matches_fixture(client, rider):
    bus = client.get("/buses", params={"route_id": "5E"}).json()[0]
    r = client.post("/crowding", json={"bus_id": bus["id"], "route_id": "5E", "level": "ok"}, headers=rider)
    assert r.status_code == 201
    same_shape(r.json(), fixture("crowding.json"))


def test_errors_use_contract_body(client, op, rider):
    r = client.get("/state")
    assert r.status_code == 401 and set(r.json()["error"]) == {"code", "message"}
    assert client.get("/state", headers=rider).status_code == 403
    r = client.post("/decisions", json={"recommendation_id": "rec_9999", "decision": "approve"}, headers=op)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = client.post("/clock", json={"action": "fly"}, headers=op)
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_request"
