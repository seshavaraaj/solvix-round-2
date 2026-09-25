"""Synthetic ticket-machine (ETM) boardings for the history days (plan B1.6,
solution2 §6.3).

boardings(stop, 15-min band) ~ Poisson(rate x 15 x day noise), where rate is
the documented DemandModel formula (demand_params.yaml) with the day's
weather, day type and planned events. Some days also get an unannounced
surge (not in the event calendar) so the forecast must use recent boardings.

ETM schema (real ETM exports aggregated to this shape replace the file with no
code changes):
    date, route_id, direction, stop_seq, stop_id, band, boardings

Writes data/artefacts/history/{boardings,events}.parquet.

Run: python offline/data_prep/synthetic_etm.py
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ARTEFACTS  # noqa: E402

from app.core.demand import DemandModel  # noqa: E402
from app.core.features import BAND_MIN, N_BANDS_DAY  # noqa: E402
from app.core.network import load_network  # noqa: E402
from app.core.timeutil import day_type  # noqa: E402
from app.core.traveltime import TravelTime  # noqa: E402

FIRST_BAND = 5 * 60 // BAND_MIN     # 05:00
LAST_BAND = 23 * 60 // BAND_MIN     # 23:00


def history_dates(start: str, end: str, exclude: set[str]) -> list[str]:
    d, stop, out = date.fromisoformat(start), date.fromisoformat(end), []
    while d <= stop:
        if d.isoformat() not in exclude:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def random_events(rng: np.random.Generator, net, day: str) -> tuple[list[dict], list[dict]]:
    """(planned events known in advance, unannounced surges)."""
    hubs = [s.id for s in net.stops.values() if s.type in ("hub", "commercial")]
    planned, hidden = [], []
    if rng.random() < 0.25:
        start = int(rng.integers(10 * 4, 20 * 4)) * BAND_MIN
        planned.append({"date": day, "stops": list(rng.choice(hubs, size=int(rng.integers(1, 3)), replace=False)),
                        "start_min": float(start), "end_min": float(start + int(rng.integers(6, 10)) * BAND_MIN),
                        "factor": round(float(rng.uniform(1.6, 3.0)), 2), "planned": True})
    if rng.random() < 0.15:
        start = int(rng.integers(8 * 4, 21 * 4)) * BAND_MIN
        hidden.append({"date": day, "stops": list(rng.choice(hubs, size=1)), "start_min": float(start),
                       "end_min": float(start + int(rng.integers(4, 8)) * BAND_MIN),
                       "factor": round(float(rng.uniform(1.5, 2.5)), 2), "planned": False})
    return planned, hidden


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-07-01")
    ap.add_argument("--end", default="2026-09-21")
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    net = load_network(ARTEFACTS)
    tt = TravelTime(net)
    dm = DemandModel(net, tt)
    holidays = net.config.get("holidays", [])
    scen_dates = {s["date"] for s in net.scenarios["scenarios"].values()}
    weather = pl.read_parquet(ARTEFACTS / "history" / "weather.parquet")
    rain_by = {(r["date"], r["hour"]): r["rain_mm"] for r in weather.iter_rows(named=True)}
    rng = np.random.default_rng(args.seed)

    rows = {k: [] for k in ("date", "route_id", "direction", "stop_seq", "stop_id", "band", "boardings")}
    ev_rows = []
    for day in history_dates(args.start, args.end, scen_dates):
        dt = day_type(day, holidays)
        planned, hidden = random_events(rng, net, day)
        ev_rows += planned + hidden
        all_events = planned + hidden
        for rid, r in net.routes.items():
            route_day = float(rng.lognormal(0, 0.10))          # day-to-day route noise
            for d in (0, 1):
                stops = r.stops(d)
                for band in range(FIRST_BAND, LAST_BAND):
                    minute = band * BAND_MIN + BAND_MIN / 2
                    rain = rain_by.get((day, int(minute // 60)), 0.0)
                    rate = dm.board_rate(rid, d, minute, dt, rain, all_events, route_day)
                    counts = rng.poisson(rate * BAND_MIN)
                    for i, c in enumerate(counts[:-1]):
                        rows["date"].append(day)
                        rows["route_id"].append(rid)
                        rows["direction"].append(d)
                        rows["stop_seq"].append(i)
                        rows["stop_id"].append(stops[i])
                        rows["band"].append(band)
                        rows["boardings"].append(int(c))
    out = ARTEFACTS / "history"
    out.mkdir(parents=True, exist_ok=True)
    df = pl.DataFrame(rows, schema_overrides={"direction": pl.Int8, "stop_seq": pl.Int16, "band": pl.Int16,
                                              "boardings": pl.Int32})
    df.write_parquet(out / "boardings.parquet", compression="zstd")
    pl.DataFrame(ev_rows, schema={"date": pl.Utf8, "stops": pl.List(pl.Utf8), "start_min": pl.Float64,
                                  "end_min": pl.Float64, "factor": pl.Float64, "planned": pl.Boolean}
                 ).write_parquet(out / "events.parquet")
    assert N_BANDS_DAY == 96
    print(f"boardings: {df.height} rows over {df['date'].n_unique()} days; events: {len(ev_rows)}")


if __name__ == "__main__":
    main()
