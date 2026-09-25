"""Hourly weather for the history and scenario days (plan B1.7).

Source: Open-Meteo historical archive (free, no key). If the request fails
(offline laptop), a seeded monsoon-season generator fills the gap so the
pipeline still runs; the output says which source was used.

Writes data/artefacts/history/weather.parquet: date, hour, rain_mm, temp_c, source.

Run: python offline/data_prep/weather.py --start 2026-07-01 --end 2026-09-21
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import ARTEFACTS  # noqa: E402

DELHI = (28.61, 77.21)
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"


def fetch_open_meteo(start: str, end: str) -> pl.DataFrame:
    q = urllib.parse.urlencode({
        "latitude": DELHI[0], "longitude": DELHI[1], "start_date": start, "end_date": end,
        "hourly": "precipitation,temperature_2m", "timezone": "Asia/Kolkata",
    })
    with urllib.request.urlopen(f"{ARCHIVE}?{q}", timeout=30) as resp:
        data = json.loads(resp.read().decode())
    h = data["hourly"]
    rows = []
    for ts, rain, temp in zip(h["time"], h["precipitation"], h["temperature_2m"]):
        if rain is None or temp is None:
            continue
        rows.append({"date": ts[:10], "hour": int(ts[11:13]), "rain_mm": float(rain), "temp_c": float(temp),
                     "source": "open-meteo"})
    return pl.DataFrame(rows)


def synthetic_weather(start: str, end: str, seed: int = 7) -> pl.DataFrame:
    """Monsoon-like: ~35% of days get a 1–4 hour afternoon/evening shower."""
    rng = np.random.default_rng(seed)
    rows = []
    d, stop = date.fromisoformat(start), date.fromisoformat(end)
    while d <= stop:
        rain = np.zeros(24)
        if rng.random() < 0.35:
            s = int(rng.integers(12, 20))
            dur = int(rng.integers(1, 5))
            rain[s:s + dur] = rng.gamma(1.5, 3.0, size=len(rain[s:s + dur]))
        base = rng.normal(31, 2)
        for hr in range(24):
            temp = base + 4 * np.sin((hr - 9) / 24 * 2 * np.pi) - 0.6 * rain[hr]
            rows.append({"date": d.isoformat(), "hour": hr, "rain_mm": round(float(rain[hr]), 2),
                         "temp_c": round(float(temp), 1), "source": "synthetic"})
        d += timedelta(days=1)
    return pl.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-07-01")
    ap.add_argument("--end", default="2026-09-21")
    ap.add_argument("--synthetic", action="store_true", help="skip the Open-Meteo request")
    args = ap.parse_args()
    out = ARTEFACTS / "history"
    out.mkdir(parents=True, exist_ok=True)
    df = None
    if not args.synthetic:
        try:
            df = fetch_open_meteo(args.start, args.end)
            if df.height == 0:
                df = None
        except Exception as exc:  # network down, date not yet in archive, ...
            print(f"Open-Meteo unavailable ({exc}); using synthetic weather")
    if df is None:
        df = synthetic_weather(args.start, args.end)
    df.write_parquet(out / "weather.parquet")
    print(f"weather: {df.height} rows, source={df['source'][0]}")


if __name__ == "__main__":
    main()
