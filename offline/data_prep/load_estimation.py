"""Load estimation for replay days (plan B1.8, solution2 §6.2).

ETM data has boardings only. For each trip: seed OD = boardings x
attraction-based destination shares; balance with IPF against attraction
column margins; on-board load after each stop = cumulative boardings minus
cumulative alightings. Adds `load_est` (passengers) to the stop events.

The API shows `load_est`, never the simulator's true `load`, so the demo uses
the same information a real operator would have.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402,F401

from app.core.demand import DemandModel  # noqa: E402
from app.core.loads import ipf_trip, onboard_from_od  # noqa: E402
from app.core.network import Network  # noqa: E402


def estimate_loads(events: pl.DataFrame, net: Network, dm: DemandModel) -> pl.DataFrame:
    out = []
    for (trip_id,), g in events.sort(["trip_id", "stop_seq"]).group_by(["trip_id"], maintain_order=True):
        rid = g["route_id"][0]
        d = int(g["direction"][0])
        n = len(net.routes[rid].stop_ids)
        minute = float(g["arr_s"][0]) / 60
        b = np.zeros(n)
        seqs = g["stop_seq"].to_numpy()
        b[seqs] = g["boardings"].to_numpy()
        _, alight_w = dm._weights(rid, d, minute)
        od = ipf_trip(b, dm.dest_probs(rid, d, minute), alight_w)
        onboard = onboard_from_od(od)
        out.append(g.with_columns(pl.Series("load_est", np.round(onboard[seqs], 2))))
    return pl.concat(out).sort(["bus_id", "arr_s"])


def main() -> None:
    from common import ARTEFACTS

    from app.core.network import load_network
    from app.core.traveltime import TravelTime

    net = load_network(ARTEFACTS)
    dm = DemandModel(net, TravelTime(net))
    for path in sorted((ARTEFACTS / "replay").glob("*/events.parquet")):
        ev = estimate_loads(pl.read_parquet(path).drop("load_est", strict=False), net, dm)
        ev.write_parquet(path)
        err = (ev["load_est"] - ev["load"]).abs().mean()
        print(f"{path.parent.name}: mean |estimated - true| load = {err:.1f} passengers")


if __name__ == "__main__":
    main()
