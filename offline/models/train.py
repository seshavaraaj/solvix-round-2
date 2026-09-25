"""Train the LightGBM demand (quantile P50/P90) and travel-time models
(plan B2.2–B2.4). Features come from api/app/core/features.py so training and
inference share the same code.

Inputs:  data/artefacts/history/{boardings,segments,weather,events}.parquet
Outputs: data/artefacts/models/{demand_p50,demand_p90,traveltime}.txt,
         data/artefacts/models/meta.json, offline/models/metrics.md

Run: python offline/models/train.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import lightgbm as lgb
import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ARTEFACTS, REPO  # noqa: E402

from app.core.demand import DemandModel  # noqa: E402
from app.core.features import (DEMAND_CATEGORICAL, DEMAND_FEATURES, LAG_BANDS, N_BANDS_DAY, N_GROUPS,  # noqa: E402
                               TT_CATEGORICAL, TT_FEATURES, BaseDemand, demand_matrix, event_factor,
                               route_codes, stop_groups, tt_matrix)
from app.core.network import load_network  # noqa: E402
from app.core.traveltime import TravelTime  # noqa: E402

VALID_DAYS = 14
HORIZONS = range(1, 9)             # 15 .. 120 minutes ahead
NOW_BANDS = range(6 * 4, 22 * 4, 2)


def pinball(y: np.ndarray, q: np.ndarray, alpha: float) -> float:
    d = y - q
    return float(np.mean(np.maximum(alpha * d, (alpha - 1) * d)))


def demand_dataset(net, dm) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    codes = route_codes(net)
    base = BaseDemand(net, dm)
    b = pl.read_parquet(ARTEFACTS / "history" / "boardings.parquet")
    weather = pl.read_parquet(ARTEFACTS / "history" / "weather.parquet")
    events = pl.read_parquet(ARTEFACTS / "history" / "events.parquet").filter(pl.col("planned"))
    holidays = set(net.config.get("holidays", []))

    keys = [(rid, d, g) for rid in sorted(net.routes) for d in (0, 1) for g in range(N_GROUPS)]
    kidx = {k: i for i, k in enumerate(keys)}
    group_of = {(rid, d): stop_groups(len(net.routes[rid].stop_ids)) for rid in net.routes for d in (0, 1)}
    b = b.with_columns(
        pl.struct(["route_id", "direction", "stop_seq"]).map_elements(
            lambda s: int(group_of[s["route_id"], s["direction"]][s["stop_seq"]]), return_dtype=pl.Int8
        ).alias("group"))
    agg = b.group_by(["date", "route_id", "direction", "group", "band"]).agg(pl.col("boardings").sum())
    dates = sorted(agg["date"].unique().to_list())
    D = {d: i for i, d in enumerate(dates)}
    cube = np.zeros((len(dates), len(keys), N_BANDS_DAY))
    for r in agg.iter_rows(named=True):
        cube[D[r["date"]], kidx[r["route_id"], r["direction"], r["group"]], r["band"]] = r["boardings"]
    rain = np.zeros((len(dates), 24))
    temp = np.full((len(dates), 24), 30.0)
    for r in weather.iter_rows(named=True):
        if r["date"] in D:
            rain[D[r["date"]], r["hour"]] = r["rain_mm"]
            temp[D[r["date"]], r["hour"]] = r["temp_c"]
    evf = np.ones((len(dates), len(keys), N_BANDS_DAY))
    for day, g in events.group_by("date"):
        day = day[0]
        if day not in D:
            continue
        evs = g.to_dicts()
        for ki, (rid, d, grp) in enumerate(keys):
            for band in range(N_BANDS_DAY):
                evf[D[day], ki, band] = event_factor(dm, evs, rid, d, grp, band)
    base_arr = np.array([[base.get(rid, d, g, band) for band in range(N_BANDS_DAY)] for rid, d, g in keys])
    lag_typ = np.array([[base.lag(rid, d, g, band) for band in range(N_BANDS_DAY)] for rid, d, g in keys])

    cols = {f: [] for f in DEMAND_FEATURES}
    ys, day_idx = [], []
    k_route = np.array([codes[k[0]] for k in keys])
    k_dir = np.array([k[1] for k in keys])
    k_grp = np.array([k[2] for k in keys])
    for di, day in enumerate(dates):
        dow = date.fromisoformat(day).weekday()
        hol = 1.0 if day in holidays else 0.0
        for n0 in NOW_BANDS:
            lag = cube[di, :, n0 - LAG_BANDS:n0].sum(axis=1)
            for h in HORIZONS:
                band = n0 + h
                if band >= N_BANDS_DAY - 4:
                    continue
                hour = band * 15 // 60
                n = len(keys)
                cols["route_code"].append(k_route)
                cols["direction"].append(k_dir)
                cols["stop_group"].append(k_grp)
                cols["band"].append(np.full(n, band))
                cols["dow"].append(np.full(n, dow))
                cols["is_holiday"].append(np.full(n, hol))
                cols["rain_mm"].append(np.full(n, rain[di, hour]))
                cols["temp_c"].append(np.full(n, temp[di, hour]))
                cols["event_factor"].append(evf[di, :, band])
                cols["horizon"].append(np.full(n, h))
                cols["base_target"].append(base_arr[:, band])
                cols["lag_60"].append(lag)
                cols["typical_lag_60"].append(lag_typ[:, n0])
                ys.append(cube[di, :, band])
                day_idx.append(np.full(n, di))
    X = demand_matrix({k: np.concatenate(v) for k, v in cols.items()})
    y = np.concatenate(ys)
    days = np.concatenate(day_idx)
    base_col = X[:, DEMAND_FEATURES.index("base_target")]
    weight = 1.0 + 2.0 * (y > 1.3 * base_col)              # emphasise rare high-load rows
    return X, y, days, weight


def travel_dataset(net, tt) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    codes = route_codes(net)
    seg = pl.read_parquet(ARTEFACTS / "history" / "segments.parquet")
    weather = pl.read_parquet(ARTEFACTS / "history" / "weather.parquet").select(["date", "hour", "rain_mm"])
    norm_rows = []
    for rid, r in net.routes.items():
        for d in (0, 1):
            km = r.seg_km(d)
            for band in range(N_BANDS_DAY):
                ns = tt.seg_times_s(rid, d, band * 15 + 7.5)
                for i in range(len(km)):
                    norm_rows.append({"route_id": rid, "direction": d, "seg_idx": i, "band": band,
                                      "norm_s": float(ns[i]), "seg_km": float(km[i])})
    norms = pl.DataFrame(norm_rows, schema_overrides={"direction": pl.Int8, "seg_idx": pl.Int16, "band": pl.Int16})
    df = seg.join(norms, on=["route_id", "direction", "seg_idx", "band"])
    ratio = (df.group_by(["date", "route_id", "direction", "band"])
             .agg((pl.col("run_s") / pl.col("norm_s")).mean().alias("ratio"))
             .sort(["date", "route_id", "direction", "band"])
             .with_columns(((pl.col("ratio").shift(1) + pl.col("ratio").shift(2)) / 2)
                           .over(["date", "route_id", "direction"]).alias("recent_speed_ratio")))
    df = (df.join(ratio.select(["date", "route_id", "direction", "band", "recent_speed_ratio"]),
                  on=["date", "route_id", "direction", "band"])
          .drop_nulls("recent_speed_ratio")
          .with_columns((pl.col("band") * 15 // 60).alias("hour"),
                        pl.col("date").map_elements(lambda s: date.fromisoformat(s).weekday(),
                                                    return_dtype=pl.Int8).alias("dow"),
                        pl.col("route_id").replace_strict(codes, return_dtype=pl.Int16).alias("route_code"))
          .join(weather, on=["date", "hour"], how="left")
          .with_columns(pl.col("rain_mm").fill_null(0.0)))
    dates = sorted(df["date"].unique().to_list())
    D = {d: i for i, d in enumerate(dates)}
    X = tt_matrix({f: df[f].to_numpy() for f in TT_FEATURES})
    return X, df["run_s"].to_numpy(), np.array([D[d] for d in df["date"].to_list()])


def train_quantile(X, y, w, alpha, cat_idx, valid_mask):
    params = {"objective": "quantile", "alpha": alpha, "learning_rate": 0.05, "num_leaves": 31,
              "min_data_in_leaf": 50, "feature_fraction": 0.9, "bagging_fraction": 0.8, "bagging_freq": 1,
              "verbose": -1, "num_threads": 2, "seed": 1}
    tr = lgb.Dataset(X[~valid_mask], y[~valid_mask], weight=w[~valid_mask], categorical_feature=cat_idx,
                     free_raw_data=False)
    va = lgb.Dataset(X[valid_mask], y[valid_mask], reference=tr, categorical_feature=cat_idx)
    return lgb.train(params, tr, num_boost_round=400, valid_sets=[va],
                     callbacks=[lgb.early_stopping(30, verbose=False)])


def main() -> None:
    net = load_network(ARTEFACTS)
    tt = TravelTime(net)
    dm = DemandModel(net, tt)
    out = ARTEFACTS / "models"
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# Model metrics", "", "Generated by `offline/models/train.py`. Validation = last "
             f"{VALID_DAYS} history days (time-based split).", ""]

    X, y, days, w = demand_dataset(net, dm)
    valid = days >= days.max() - VALID_DAYS + 1
    cat = [DEMAND_FEATURES.index(c) for c in DEMAND_CATEGORICAL]
    m50 = train_quantile(X, y, w, 0.5, cat, valid)
    m90 = train_quantile(X, y, w, 0.9, cat, valid)
    p50, p90 = m50.predict(X[valid]), m90.predict(X[valid])
    yv = y[valid]
    naive = X[valid, DEMAND_FEATURES.index("base_target")]
    lines += ["## Demand (boardings per route-direction-stop group-15 min)", "",
              f"Rows: {len(y):,} train+valid, {valid.sum():,} valid.", "",
              "| Metric | Value |", "|---|---|",
              f"| MAE P50 | {np.mean(np.abs(yv - p50)):.2f} |",
              f"| MAE calendar baseline (formula, no model) | {np.mean(np.abs(yv - naive)):.2f} |",
              f"| Pinball loss P50 | {pinball(yv, p50, 0.5):.3f} |",
              f"| Pinball loss P90 | {pinball(yv, p90, 0.9):.3f} |",
              f"| P90 coverage (share of actuals <= P90) | {np.mean(yv <= p90):.3f} |",
              f"| Mean target | {yv.mean():.2f} |", ""]
    m50.save_model(str(out / "demand_p50.txt"))
    m90.save_model(str(out / "demand_p90.txt"))

    Xt, yt, dt = travel_dataset(net, tt)
    valid_t = dt >= dt.max() - VALID_DAYS + 1
    cat_t = [TT_FEATURES.index(c) for c in TT_CATEGORICAL]
    params = {"objective": "regression_l1", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 50,
              "verbose": -1, "num_threads": 2, "seed": 1}
    tr = lgb.Dataset(Xt[~valid_t], yt[~valid_t], categorical_feature=cat_t, free_raw_data=False)
    va = lgb.Dataset(Xt[valid_t], yt[valid_t], reference=tr, categorical_feature=cat_t)
    mt = lgb.train(params, tr, num_boost_round=400, valid_sets=[va], callbacks=[lgb.early_stopping(30, verbose=False)])
    pt = mt.predict(Xt[valid_t])
    ytv = yt[valid_t]
    lines += ["## Travel time (segment running time, seconds)", "",
              f"Rows: {len(yt):,} train+valid, {valid_t.sum():,} valid.", "",
              "| Metric | Value |", "|---|---|",
              f"| MAE | {np.mean(np.abs(ytv - pt)):.1f} s |",
              f"| MAPE | {np.mean(np.abs(ytv - pt) / ytv) * 100:.1f} % |",
              f"| Mean target | {ytv.mean():.1f} s |", ""]
    mt.save_model(str(out / "traveltime.txt"))

    meta = {"demand_features": DEMAND_FEATURES, "tt_features": TT_FEATURES, "route_codes": route_codes(net),
            "demand_best_iter": [m50.best_iteration, m90.best_iteration], "tt_best_iter": mt.best_iteration}
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    lines += ["Data is synthetic until real ETM and recorded GTFS-RT are available (see README).", ""]
    (REPO / "offline" / "models" / "metrics.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
