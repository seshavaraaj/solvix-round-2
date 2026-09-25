"""Stack validation for Render free (plan B0.4): import LightGBM, OR-Tools,
Polars and SimPy, load the models, solve one CP-SAT model, run the API
start-up and one /state + /cycle + /whatif, and report memory and timings.

Run locally or in a Render shell:  python scripts/toy_load_test.py
Record the numbers in README.md (target <= 350 MB idle, 512 MB limit).
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "api"))
sys.path.insert(0, str(REPO / "scripts"))
warnings.filterwarnings("ignore")


def rss_mb() -> float:
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        pass
    try:  # Windows / macOS fallback
        import psutil

        return psutil.Process().memory_info().rss / 2 ** 20
    except ImportError:
        return float("nan")


def step(label: str, t0: float) -> float:
    print(f"{label:38s} {time.perf_counter() - t0:6.2f} s   RSS {rss_mb():6.0f} MB", flush=True)
    return time.perf_counter()


def main() -> None:
    t = time.perf_counter()
    step("python start", t)
    import lightgbm  # noqa: F401
    import polars  # noqa: F401
    import simpy  # noqa: F401
    from ortools.sat.python import cp_model

    t = step("import lightgbm, polars, simpy, ortools", t)
    m = cp_model.CpModel()
    x = [m.NewIntVar(0, 10, f"x{i}") for i in range(50)]
    m.Add(sum(x) <= 100)
    m.Maximize(sum((i % 7) * v for i, v in enumerate(x)))
    s = cp_model.CpSolver()
    s.parameters.num_workers = 1
    s.parameters.max_time_in_seconds = 5
    s.Solve(m)
    t = step("toy CP-SAT solve", t)

    os.environ.setdefault("DATABASE_URL", f"sqlite:///{(Path(tempfile.mkdtemp()) / 'toy.db').as_posix()}")
    os.environ.setdefault("OPERATOR_PASSWORD", "toy")
    os.environ.setdefault("JWT_SECRET", "toy-secret-0123456789abcdef0123456789abcdef")
    import seed_db
    from fastapi.testclient import TestClient

    from app.main import app

    seed_db.seed(reset_config=False)
    with TestClient(app) as c:
        while c.get("/health").json()["status"] != "ok":
            time.sleep(0.1)
        t = step("API start-up (artefacts + models)", t)
        h = {"Authorization": "Bearer " + c.post("/auth/login", json={
            "username": "operator", "password": os.environ["OPERATOR_PASSWORD"]}).json()["token"]}
        c.post("/clock", json={"action": "jump", "scenario": "event_surge", "t": "2026-09-25T17:15:00+05:30"},
               headers=h)
        c.get("/state", headers=h)
        t = step("GET /state", t)
        recs = c.post("/cycle", headers=h).json()["recommendations"]
        t = step("POST /cycle (forecast+detect+CP-SAT)", t)
        if recs:
            c.post("/whatif", json={"recommendation_id": recs[0]["id"]}, headers=h)
            step("POST /whatif (2 x 2 simulations)", t)
    print(f"peak-ish RSS after demo calls: {rss_mb():.0f} MB")


if __name__ == "__main__":
    main()
