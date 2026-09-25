"""Derive segment running times, headways and delays (plan B1.5).

Two sources, same output schema:
- real:      data/raw/rt_clean/<date>.parquet (from clean_rt.py) -> stop passages
             by interpolating each bus's distance along the route;
- synthetic: (default when no cleaned recording exists) segment times from the
             physical travel-time model x weather x route-day noise x random
             incidents, so the travel-time model has history to learn from.

Writes data/artefacts/history/segments.parquet:
    date, route_id, direction, seg_idx, band, run_s
and, for real recordings, data/raw/rt_clean/<date>_passages.parquet:
    bus_id, trip_id, route_id, direction, stop_seq, stop_id, arr_s, dep_s

Run: python offline/data_prep/derive.py [--real 2026-09-23 ...]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ARTEFACTS, RAW  # noqa: E402
from data_prep.synthetic_etm import FIRST_BAND, LAST_BAND, history_dates  # noqa: E402

from app.core.features import BAND_MIN  # noqa: E402
from app.core.network import load_network  # noqa: E402
from app.core.traveltime import TravelTime  # noqa: E402


def passages_from_clean(day: str) -> pl.DataFrame:
    """Stop passage times from cleaned positions (linear interpolation)."""
    net = load_network(ARTEFACTS)
    df = pl.read_parquet(RAW / "rt_clean" / f"{day}.parquet").sort(["bus_id", "t_s"])
    rows = []
    for (bus_id,), g in df.group_by(["bus_id"], maintain_order=True):
        recs = g.to_dicts()
        trip_no = 0
        for a, b in zip(recs, recs[1:]):
            if a["direction"] != b["direction"] or a["route_id"] != b["route_id"]:
                trip_no += 1
                continue
            r = net.routes[a["route_id"]]
            km = r.stop_km(a["direction"])
            for i, k in enumerate(km):
                if a["dist_km"] < k <= b["dist_km"] and b["dist_km"] > a["dist_km"]:
                    f = (k - a["dist_km"]) / (b["dist_km"] - a["dist_km"])
                    t = a["t_s"] + f * (b["t_s"] - a["t_s"])
                    rows.append({"bus_id": bus_id, "trip_id": f"{bus_id}_{trip_no}", "route_id": r.id,
                                 "direction": a["direction"], "stop_seq": i, "stop_id": r.stops(a["direction"])[i],
                                 "arr_s": round(t, 1), "dep_s": round(t, 1)})
    return pl.DataFrame(rows)


def segments_from_passages(day: str, passages: pl.DataFrame) -> pl.DataFrame:
    p = passages.sort(["trip_id", "stop_seq"])
    p = p.with_columns(
        pl.col("arr_s").shift(-1).over("trip_id").alias("next_arr"),
        pl.col("stop_seq").shift(-1).over("trip_id").alias("next_seq"),
    ).filter(pl.col("next_seq") == pl.col("stop_seq") + 1)
    return (p.with_columns(((pl.col("next_arr") - pl.col("dep_s"))).alias("run_s"),
                           (pl.col("dep_s") // (BAND_MIN * 60)).cast(pl.Int16).alias("band"))
            .group_by(["route_id", "direction", "stop_seq", "band"])
            .agg(pl.col("run_s").mean())
            .rename({"stop_seq": "seg_idx"})
            .with_columns(pl.lit(day).alias("date")))


def synthetic_segments(start: str, end: str, seed: int = 13) -> pl.DataFrame:
    net = load_network(ARTEFACTS)
    tt = TravelTime(net)
    rng = np.random.default_rng(seed)
    scen = {s["date"] for s in net.scenarios["scenarios"].values()}
    weather = pl.read_parquet(ARTEFACTS / "history" / "weather.parquet")
    rain_by = {(r["date"], r["hour"]): r["rain_mm"] for r in weather.iter_rows(named=True)}
    cols = {k: [] for k in ("date", "route_id", "direction", "seg_idx", "band", "run_s")}
    for day in history_dates(start, end, scen):
        incident = None
        if rng.random() < 0.3:   # one route slows down for 1–2 hours
            rid = str(rng.choice(sorted(net.routes)))
            b0 = int(rng.integers(FIRST_BAND + 8, LAST_BAND - 8))
            incident = (rid, b0, b0 + int(rng.integers(4, 9)), float(rng.uniform(1.3, 1.7)))
        for rid in net.routes:
            day_f = float(rng.lognormal(0, 0.06))
            for d in (0, 1):
                for band in range(FIRST_BAND, LAST_BAND):
                    minute = band * BAND_MIN + BAND_MIN / 2
                    rain = rain_by.get((day, int(minute // 60)), 0.0)
                    base = tt.seg_times_s(rid, d, minute, tt.rain_speed_factor(rain))
                    f = day_f
                    if incident and incident[0] == rid and incident[1] <= band < incident[2]:
                        f *= incident[3]
                    noise = rng.lognormal(0, tt.noise_cv / np.sqrt(3), size=len(base))
                    for i, v in enumerate(base * f * noise):
                        cols["date"].append(day)
                        cols["route_id"].append(rid)
                        cols["direction"].append(d)
                        cols["seg_idx"].append(i)
                        cols["band"].append(band)
                        cols["run_s"].append(round(float(v), 1))
    return pl.DataFrame(cols, schema_overrides={"direction": pl.Int8, "seg_idx": pl.Int16, "band": pl.Int16})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", nargs="*", default=[], help="dates with cleaned RT recordings")
    ap.add_argument("--start", default="2026-07-01")
    ap.add_argument("--end", default="2026-09-21")
    args = ap.parse_args()
    out = ARTEFACTS / "history"
    out.mkdir(parents=True, exist_ok=True)
    if args.real:
        parts = []
        for day in args.real:
            p = passages_from_clean(day)
            p.write_parquet(RAW / "rt_clean" / f"{day}_passages.parquet")
            parts.append(segments_from_passages(day, p))
        seg = pl.concat(parts, how="vertical_relaxed")
    else:
        seg = synthetic_segments(args.start, args.end)
    seg.write_parquet(out / "segments.parquet", compression="zstd")
    print(f"segments: {seg.height} rows")


if __name__ == "__main__":
    main()
