"""Plain-text explanations from Jinja2 templates (plan B4.4, solution2 §6.7).
Every number in the text comes from the recommendation record."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .timeutil import hhmm, parse_iso

_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).resolve().parents[1] / "templates")),
    undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True, autoescape=False,
)


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{round(x * 100):d}%"


def _num(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"{x:.0f}" if abs(x - round(x)) < 0.05 else f"{x:.1f}"


_env.filters["pct"] = _pct
_env.filters["num"] = _num


def explain(rec: dict, context: dict) -> str:
    """rec: Recommendation dict (contract §5). context: route names, min headways
    and the evidence stop taken from the trigger flags."""
    t0 = hhmm(parse_iso(rec["window_start"])[1])
    t1 = hhmm(parse_iso(rec["window_end"])[1])
    text = _env.get_template(f"{rec['action']}.j2").render(r=rec, c=context, start=t0, end=t1)
    return " ".join(text.split())
