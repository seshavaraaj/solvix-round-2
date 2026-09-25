"""Rebuild every artefact in data/artefacts/ in order (offline lane, laptop).

  1. gtfs_subset     Chennai GTFS route cluster -> gtfs/*.parquet, config.json
  2. weather         Open-Meteo history (synthetic fallback when offline)
  3. synthetic_etm   history boardings (ETM stand-in)
  4. derive          history segment running times
  5. build_replay    replay days for the API (+ load estimation)
  6. models/train    LightGBM demand P50/P90 + travel time
  7. sim/run_batch   scenario x strategy x error results.json
  8. mock fixtures   regenerated from the real API

Run: python offline/run_all.py [--skip-network] [--seeds 5]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    t0 = time.perf_counter()
    print(f"\n== {' '.join(args)}", flush=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    subprocess.run([sys.executable, *args], cwd=REPO, check=True, env=env)
    print(f"   done in {time.perf_counter() - t0:.0f}s", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-network", action="store_true", help="keep gtfs/ from an earlier gtfs_subset.py run")
    ap.add_argument("--seeds", default="5")
    args = ap.parse_args()
    if not args.skip_network:
        run("offline/data_prep/gtfs_subset.py")
    run("offline/data_prep/weather.py")
    run("offline/data_prep/synthetic_etm.py")
    run("offline/data_prep/derive.py")
    run("offline/data_prep/build_replay.py")
    run("offline/models/train.py")
    run("offline/sim/run_batch.py", "--seeds", args.seeds)
    run("mock/make_fixtures.py")
    total = sum(p.stat().st_size for p in (REPO / "data" / "artefacts").rglob("*") if p.is_file())
    print(f"\ndata/artefacts: {total / 2 ** 20:.1f} MB (limit 100 MB)")


if __name__ == "__main__":
    main()
