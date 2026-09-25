"""Scripted demo flows (plan Testing: integration; contract §9 joint tests)."""
import time


def test_event_surge_flow(client, op):
    """/clock jump -> /cycle -> /decisions -> /whatif -> map reflects the move (M2, M3)."""
    r = client.post("/clock", json={"action": "jump", "scenario": "event_surge",
                                    "t": "2026-09-25T17:10:00+05:30"}, headers=op)
    assert r.json()["t"] == "2026-09-25T17:10:00+05:30" and r.json()["playing"] is False

    t0 = time.perf_counter()
    cyc = client.post("/cycle", headers=op).json()
    assert time.perf_counter() - t0 < 10
    assert cyc["ran"] is True
    move = next(r for r in cyc["recommendations"] if r["action"] == "move_bus" and r["to_route_id"] == "3")
    assert "overcrowded" in move["trigger_flags"]
    assert move["explanation"].startswith(f"Move {move['bus_count']} bus")
    assert client.post("/cycle", headers=op).json()["ran"] is False          # < 15 simulated minutes

    t0 = time.perf_counter()
    w = client.post("/whatif", json={"recommendation_id": move["id"]}, headers=op).json()
    assert time.perf_counter() - t0 < 10
    assert w["with"]["overload_min"] <= w["without"]["overload_min"]

    before = client.get("/state", params={"t": "2026-09-25T18:00:00+05:30"}, headers=op).json()
    n_before = sum(b["route_id"] == "3" for b in before["buses"])
    d = client.post("/decisions", json={"recommendation_id": move["id"], "decision": "approve"}, headers=op)
    assert d.status_code == 201
    assert client.post("/decisions", json={"recommendation_id": move["id"], "decision": "reject",
                                           "reason": "other"}, headers=op).status_code == 409
    after = client.get("/state", params={"t": "2026-09-25T18:00:00+05:30"}, headers=op).json()
    assert sum(b["route_id"] == "3" for b in after["buses"]) == n_before + move["bus_count"]
    alerts = client.get("/alerts", params={"route_id": "3"}).json()
    assert any(a["kind"] == "service_change" for a in alerts)

    # a new cycle expires older pending cards
    client.post("/clock", json={"action": "jump", "t": "2026-09-25T17:40:00+05:30"}, headers=op)
    client.post("/cycle", headers=op)
    statuses = {r["id"]: r["status"] for r in client.get("/recommendations", headers=op).json()}
    assert statuses[move["id"]] == "approved"
    assert all(s != "pending" for rid, s in statuses.items() if rid < move["id"])


def test_rider_crowded_reports_raise_route_load(client, op, rider):
    """M4: rider "Crowded" on Route 3 raises its load on the operator map."""
    client.post("/clock", json={"action": "jump", "scenario": "normal_weekday"}, headers=op)
    before = {b["id"]: b for b in client.get("/state", headers=op).json()["buses"]}
    target = next(b for b in before.values() if b["route_id"] == "3" and b["load_factor"] > 0.2)
    r = client.post("/crowding", json={"bus_id": target["id"], "route_id": "3", "level": "crowded"},
                    headers=rider)
    assert r.status_code == 201
    assert client.post("/crowding", json={"bus_id": target["id"], "route_id": "3", "level": "crowded"},
                       headers=rider).status_code == 429
    after = {b["id"]: b for b in client.get("/state", headers=op).json()["buses"]}
    assert after[target["id"]]["load_factor"] > before[target["id"]]["load_factor"]
    assert after[target["id"]]["load_factor"] <= round(before[target["id"]]["load_factor"] * 1.3, 2) + 0.01


def test_clock_play_advances(client, op):
    client.post("/clock", json={"action": "jump", "scenario": "normal_weekday"}, headers=op)
    t0 = client.post("/clock", json={"action": "play", "speed": 30}, headers=op).json()["t"]
    time.sleep(1.2)
    t1 = client.get("/clock", headers=op).json()["t"]
    client.post("/clock", json={"action": "pause"}, headers=op)
    assert t1 > t0


def test_admin_fleet_validation(client, admin):
    bad = {"depot_id": "depot_adyar", "name": "Adyar Depot", "lat": 13.0067, "lon": 80.2532, "fleet_size": 3,
           "reserve": 4, "out_of_service": 1}
    assert client.put("/admin/fleet/depot_adyar", json=bad, headers=admin).status_code == 400
    good = {**bad, "fleet_size": 30}
    assert client.put("/admin/fleet/depot_adyar", json=good, headers=admin).json() == good
