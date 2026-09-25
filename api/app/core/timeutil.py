"""Replay time helpers. Internally time is seconds since local midnight of the
scenario date (Asia/Kolkata); on the wire it is ISO-8601 with +05:30."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def hhmm_to_s(value: str) -> int:
    h, m = value.split(":")[:2]
    return int(h) * 3600 + int(m) * 60


def to_iso(day: str | date, seconds: float) -> str:
    d = date.fromisoformat(day) if isinstance(day, str) else day
    dt = datetime(d.year, d.month, d.day, tzinfo=IST) + timedelta(seconds=int(round(seconds)))
    return dt.isoformat()


def parse_iso(value: str) -> tuple[str, int]:
    """Return (local date, seconds since local midnight) for an ISO timestamp."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    dt = dt.astimezone(IST)
    return dt.date().isoformat(), dt.hour * 3600 + dt.minute * 60 + dt.second


def now_iso() -> str:
    return datetime.now(IST).replace(microsecond=0).isoformat()


def hhmm(seconds: float) -> str:
    s = int(round(seconds)) % 86400
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}"


def day_type(day: str, holidays: list[str] | tuple[str, ...] = ()) -> str:
    if day in holidays:
        return "holiday"
    wd = date.fromisoformat(day).weekday()
    return "saturday" if wd == 5 else "sunday" if wd == 6 else "weekday"
