"""Build replay day files for the API (plan B1.9).

One folder per scenario in data/artefacts/replay/<scenario>/:
  events.parquet  stop events: bus_id, trip_id, route_id, direction, stop_seq,
                  stop_id, arr_s, dep_s, sched_s, boardings, alightings, load,
                  load_est
  dark.parquet    bus_id, start_s, end_s (no position reports in between)
  meta.json       window, fleet, bus ids, depots, driver shift ends, breakdowns

Source: until 3+ days of GTFS-RT are recorded (record_rt.py ->
clean_rt.py -> derive.py --real), the service window is generated with the
simulator's baseline strategy (fixed timetable, no control), so the replay
shows the realistic bunching and crowding that the optimiser should fix.
Boardings play the role of ETM data; load_est comes from load_estimation.py.

Run: python offline/data_prep/build_replay.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ARTEFACTS  # noqa: E402
from data_prep.load_estimation import estimate_loads  # noqa: E402

from app.core.demand import DemandModel  # noqa: E402
from app.core.network import load_network  # noqa: E402
from app.core.timeutil import day_type, hhmm_to_s  # noqa: E402
from app.core.traveltime import TravelTime  # noqa: E402
from app.sim.model import SimConfig, Simulation, planned_fleet  # noqa: E402

DARK_BUS_SHARE = 0.12


def dark_intervals(rng: np.random.Generator, bus_ids: list[str], start: int, end: int) -> list[dict]:
    rows = []
    for bid in bus_ids:
        if rng.random() < DARK_BUS_SHARE:
            for _ in range(int(rng.integers(1, 3))):
                s = int(rng.integers(start, end - 600))
                rows.append({"bus_id": bid, "start_s": s, "end_s": s + int(rng.integers(180, 540))})
    return rows


def main() -> None:
    net = load_network(ARTEFACTS)
    tt = TravelTime(net)
    dm = DemandModel(net, tt)
    sc_cfg = net.scenarios
    w0, w1 = hhmm_to_s(sc_cfg["window"]["start"]), hhmm_to_s(sc_cfg["window"]["end"])
    holidays = net.config.get("holidays", [])
    for i, (name, sc) in enumerate(sc_cfg["scenarios"].items()):
        rng = np.random.default_rng(100 + i)
        fleet = planned_fleet(net, tt)
        cfg = SimConfig(
            start_s=w0, end_s=w1 + 1800, day_type=day_type(sc["date"], holidays), rain_mm=sc["rain_mm"],
            events=dm.events_for(sc),
            breakdowns=[{"route_id": b["route_id"], "at_s": hhmm_to_s(b["at"])} for b in sc.get("breakdowns", [])],
            fleet=fleet, strategy="baseline", seed=100 + i, record=True, warmup_s=5400,
        )
        sim = Simulation(net, dm, tt, cfg)
        metrics = sim.run()
        ev = pl.DataFrame(sim.events).filter((pl.col("dep_s") >= w0 - 5400) & (pl.col("arr_s") <= w1 + 1800))
        ev = ev.with_columns(pl.col("boardings").round(0), pl.col("direction").cast(pl.Int8),
                             pl.col("stop_seq").cast(pl.Int16))
        ev = estimate_loads(ev, net, dm)
        out = ARTEFACTS / "replay" / name
        out.mkdir(parents=True, exist_ok=True)
        ev.write_parquet(out / "events.parquet", compression="zstd")
        bus_ids = sorted(ev["bus_id"].unique().to_list())
        dark = dark_intervals(rng, bus_ids, w0, w1)
        pl.DataFrame(dark, schema={"bus_id": pl.Utf8, "start_s": pl.Int32, "end_s": pl.Int32}).write_parquet(
            out / "dark.parquet")
        bus_route = {r["bus_id"]: r["route_id"] for r in ev.group_by("bus_id").agg(pl.col("route_id").first())
                     .iter_rows(named=True)}
        meta = {
            "scenario": name, "label": sc["label"], "date": sc["date"], "window_start_s": w0, "window_end_s": w1,
            "clock_start_s": hhmm_to_s(sc_cfg["clock_start"]), "rain_mm": sc["rain_mm"], "temp_c": sc["temp_c"],
            "fleet": fleet, "bus_route": bus_route,
            # simplified driver duty: shift end per bus (solution2 §6.6 duty-hour check)
            "shift_end_s": {b: int(rng.choice([hhmm_to_s("19:00"), hhmm_to_s("21:00"), hhmm_to_s("23:00")],
                                              p=[0.25, 0.35, 0.40])) for b in bus_ids},
            "breakdowns": [{"bus_id": b["bus_id"], "route_id": b["route_id"], "t_s": round(b["t_s"])}
                           for b in sim.breakdown_log],
            "baseline_metrics": metrics,
            "source": "simulated-baseline",
        }
        (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        err = (ev["load_est"] - ev["load"]).abs().mean()
        print(f"{name}: {ev.height} stop events, {len(bus_ids)} buses, {len(dark)} dark gaps, "
              f"load estimate MAE {err:.1f} pax")


if __name__ == "__main__":
    main()
