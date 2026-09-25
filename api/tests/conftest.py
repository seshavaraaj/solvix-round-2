from __future__ import annotations

import os
import sys
import tempfile
import time
import warnings
from pathlib import Path

import pytest

API = Path(__file__).resolve().parents[1]
REPO = API.parent
_db = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_db.as_posix()}"
os.environ["OPERATOR_PASSWORD"] = "op-test"
os.environ["ADMIN_PASSWORD"] = "admin-test"
os.environ["JWT_SECRET"] = "test-secret-0123456789abcdef0123456789abcdef"
sys.path.insert(0, str(API))
sys.path.insert(0, str(REPO / "scripts"))
warnings.filterwarnings("ignore", category=DeprecationWarning)


@pytest.fixture(scope="session")
def client():
    import seed_db
    from fastapi.testclient import TestClient

    from app.main import app

    seed_db.seed(reset_config=True)
    with TestClient(app) as c:
        deadline = time.time() + 60
        while c.get("/health").json()["status"] != "ok":
            assert time.time() < deadline, "API did not finish loading"
            time.sleep(0.1)
        yield c


def _token(client, user: str, pw: str) -> dict:
    tok = client.post("/auth/login", json={"username": user, "password": pw}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def op(client):
    return _token(client, "operator", "op-test")


@pytest.fixture(scope="session")
def admin(client):
    return _token(client, "admin", "admin-test")


@pytest.fixture(scope="session")
def rider(client):
    tok = client.post("/auth/device", json={"device_id": "test-device-0001"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def core():
    """Network, demand and travel-time models without the web app."""
    from app.config import settings
    from app.core.demand import DemandModel
    from app.core.network import load_network
    from app.core.traveltime import TravelTime

    net = load_network(settings.artefacts_dir)
    tt = TravelTime(net)
    return net, DemandModel(net, tt), tt
