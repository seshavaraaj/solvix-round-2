"""Offline scenario batch (plan B5.5): every scenario x strategy x forecast
error level, averaged over seeds, written to data/artefacts/results.json in
the ScenarioResult shape (contract §5). GET /results serves the file.

Run: python offline/sim/run_batch.py [--seeds 5]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ARTEFACTS  # noqa: E402

from app.core.demand import DemandModel  # noqa: E402
from app.core.network import load_network  # noqa: E402
from app.core.timeutil import hhmm_to_s  # noqa: E402
from app.core.traveltime import TravelTime  # noqa: E402
from app.sim.model import STRATEGIES, Simulation  # noqa: E402
from app.sim.strategies import ERROR_LEVELS, scenario_config  # noqa: E402

START, END = "16:30", "19:30"
INT_KEYS = ("left_behind", "overload_min", "bunching_events")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    args = ap.parse_args()
    net = load_network(ARTEFACTS)
    tt = TravelTime(net)
    dm = DemandModel(net, tt)
    scenarios = list(net.scenarios["scenarios"])
    rows = []
    t0 = time.perf_counter()
    for sc in scenarios:
        for strategy in STRATEGIES:
            # baseline and holding ignore the forecast, so run them once and repeat per error level
            levels = ERROR_LEVELS if strategy == "aduthabus" else [None]
            for level in levels:
                runs = []
                for seed in range(args.seeds):
                    cfg = scenario_config(net, dm, tt, sc, strategy, hhmm_to_s(START), hhmm_to_s(END), seed,
                                          0 if level is None else level)
                    runs.append(Simulation(net, dm, tt, cfg).run())
                agg = {k: float(np.mean([r[k] for r in runs])) for k in runs[0]}
                for k in INT_KEYS:
                    agg[k] = int(round(agg[k]))
                for k in ("avg_wait_min", "p95_wait_min", "deadhead_km", "changes_per_hour"):
                    agg[k] = round(agg[k], 2)
                agg["avg_load_factor"] = round(agg["avg_load_factor"], 3)
                for lvl in (ERROR_LEVELS if level is None else [level]):
                    rows.append({"scenario": sc, "strategy": strategy, "error_level": lvl, **agg})
                print(f"{sc:15s} {strategy:12s} err={level!s:12s} wait={agg['avg_wait_min']:5.2f} "
                      f"p95={agg['p95_wait_min']:5.2f} left={agg['left_behind']:4d} over={agg['overload_min']:4d} "
                      f"bunch={agg['bunching_events']:3d} dh={agg['deadhead_km']:5.1f}")
    result = {"scenarios": scenarios, "strategies": list(STRATEGIES), "error_levels": ERROR_LEVELS, "rows": rows}
    (ARTEFACTS / "results.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"wrote {len(rows)} rows in {time.perf_counter() - t0:.0f}s ({START}–{END}, {args.seeds} seeds)")


if __name__ == "__main__":
    main()
