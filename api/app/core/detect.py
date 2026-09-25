"""Route-health detection (plan B2.6, solution2 §6.5). Pure functions so each
flag can be unit-tested on hand-made cases.

| Flag           | Rule                                                              |
|----------------|-------------------------------------------------------------------|
| overcrowded    | forecast P90 load factor > 1.0 on any segment in the next 60 min  |
| underused      | forecast P50 load factor < 0.3 on every segment for 60 min        |
| delay_emerging | a segment > 2 sigma slower than its norm, or delay > 5 min and growing |
| bunching       | actual headway < 50% of planned between consecutive buses         |

Confidence drops one level when a dark bus is involved.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .timeutil import hhmm

OVERCROWDED_LF = 1.0
UNDERUSED_LF = 0.3
DELAY_SIGMA = 2.0
DELAY_MIN = 5.0
DELAY_GROWTH_MIN = 0.5
BUNCHING_SHARE = 0.5
LEVELS = ("low", "medium", "high")


@dataclass
class Flag:
    on: bool
    confidence: str = "high"
    evidence: str | None = None
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"on": self.on, "confidence": self.confidence, "evidence": self.evidence if self.on else None}


def lower(conf: str, steps: int = 1) -> str:
    return LEVELS[max(0, LEVELS.index(conf) - steps)]


def _window(band_starts_s: list[float], i0: int, i1: int, band_s: float) -> str:
    return f"{hhmm(band_starts_s[i0])}–{hhmm(band_starts_s[i1] + band_s)}"


def overcrowded(lf50, lf90, stop_names: list[str], band_starts_s: list[float], band_s: float = 900,
                dark: bool = False) -> Flag:
    """lf50 / lf90: (bands, segments) load factors for the next 60 minutes."""
    peak = max((max(row) for row in lf90), default=0.0)
    if peak <= OVERCROWDED_LF:
        return Flag(False, lower("high") if dark else "high")
    bi, si = max(((b, s) for b in range(len(lf90)) for s in range(len(lf90[b]))), key=lambda x: lf90[x[0]][x[1]])
    over = [b for b in range(len(lf90)) if max(lf90[b]) > OVERCROWDED_LF]
    conf = "high" if lf50[bi][si] > 0.9 else "medium"
    if dark:
        conf = lower(conf)
    ev = f"P90 load {peak:.2f} at {stop_names[si]}, {_window(band_starts_s, over[0], over[-1], band_s)}"
    return Flag(True, conf, ev, {"peak_p90": round(float(peak), 2), "stop": stop_names[si],
                                 "from_s": band_starts_s[over[0]], "to_s": band_starts_s[over[-1]] + band_s})


def underused(lf50, lf90, band_starts_s: list[float], band_s: float = 900, dark: bool = False) -> Flag:
    peak50 = max((max(row) for row in lf50), default=0.0)
    if len(lf50) * band_s < 3600 or peak50 >= UNDERUSED_LF:
        return Flag(False, lower("high") if dark else "high")
    peak90 = max((max(row) for row in lf90), default=0.0)
    conf = "high" if peak90 < 0.4 else "medium"
    if dark:
        conf = lower(conf)
    ev = f"P50 load at most {peak50:.2f} on every segment, {_window(band_starts_s, 0, len(lf50) - 1, band_s)}"
    return Flag(True, conf, ev, {"peak_p50": round(float(peak50), 2)})


def delay_emerging(segments: list[dict], delay_now_min: float, delay_prev_min: float, cv: float,
                   dark: bool = False) -> Flag:
    """segments: [{"name", "observed_s", "expected_s", "n"}] over the last 30 minutes."""
    worst, worst_z = None, 0.0
    for s in segments:
        if s["n"] <= 0 or s["expected_s"] <= 0:
            continue
        sd = cv * s["expected_s"] / math.sqrt(s["n"])
        z = (s["observed_s"] - s["expected_s"]) / sd if sd > 0 else 0.0
        if z > worst_z:
            worst, worst_z = s, z
    slow = worst is not None and worst_z > DELAY_SIGMA
    growing = delay_now_min > DELAY_MIN and delay_now_min > delay_prev_min + DELAY_GROWTH_MIN
    if not (slow or growing):
        return Flag(False, lower("medium") if dark else "medium")
    parts = []
    if growing:
        parts.append(f"Delay {delay_now_min:.1f} min, up from {delay_prev_min:.1f} min 15 min ago")
    if slow:
        parts.append(f"{worst['name']} {worst_z:.1f}σ slower than norm "
                     f"({worst['observed_s'] / 60:.1f} vs {worst['expected_s'] / 60:.1f} min)")
    conf = "high" if (slow and growing) else "medium"
    if dark:
        conf = lower(conf)
    return Flag(True, conf, "; ".join(parts), {"delay_min": round(delay_now_min, 1),
                                                "segment": worst["name"] if slow else None})


def bunching(headways: list[dict], planned_headway_min: float, dark_on_route: int = 0) -> Flag:
    """headways: [{"headway_min", "stop", "dark"}] between consecutive buses."""
    conf_off = "medium" if dark_on_route else "high"
    close = [h for h in headways if h["headway_min"] < BUNCHING_SHARE * planned_headway_min]
    if not close:
        return Flag(False, conf_off)
    worst = min(close, key=lambda h: h["headway_min"])
    if worst.get("dark"):
        conf = "low"
    elif dark_on_route:
        conf = "medium"
    else:
        conf = "high"
    ev = f"Headway {worst['headway_min']:.0f} min vs planned {planned_headway_min:.0f} min"
    if dark_on_route:
        ev += f"; {dark_on_route} dark bus" + ("es" if dark_on_route > 1 else "")
    return Flag(True, conf, ev, {"headway_min": round(worst["headway_min"], 1), "stop": worst.get("stop")})


def route_health(route_id: str, direction: int, flags: dict[str, Flag]) -> dict:
    return {"route_id": route_id, "direction": direction,
            "flags": {k: flags[k].as_dict() for k in ("overcrowded", "underused", "delay_emerging", "bunching")}}
