"""Dump decisions, recommendations and crowding reports to CSV (plan B7.2).

Run before the free Render Postgres expires (30 days after creation):
    DATABASE_URL=<external URL from the Render dashboard> python scripts/export_log.py
Output: exports/<date>/{decisions,recommendations,crowding_reports}.csv
Recreate the database afterwards with api/schema.sql + scripts/seed_db.py.
"""
from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "api"))

from sqlalchemy import select  # noqa: E402

from app import db  # noqa: E402


def main() -> None:
    out = REPO / "exports" / date.today().isoformat()
    out.mkdir(parents=True, exist_ok=True)
    with db.engine().connect() as c:
        for table in (db.decisions, db.recommendations, db.crowding_reports):
            rows = c.execute(select(table)).mappings().all()
            path = out / f"{table.name}.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=[col.name for col in table.columns])
                w.writeheader()
                w.writerows(dict(r) for r in rows)
            print(f"{path.relative_to(REPO)}: {len(rows)} rows")


if __name__ == "__main__":
    main()
