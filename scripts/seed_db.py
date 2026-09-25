"""Create tables and seed demo data (plan B3.2).

- operator / admin users with passwords from OPERATOR_PASSWORD / ADMIN_PASSWORD
  (never stored in Git; set them in .env locally or in the Render dashboard);
- routes_config and fleet_config from the GTFS subset in data/artefacts.

Idempotent: existing users get their password reset from the env; existing
config rows are kept unless --reset-config is given. The logic lives in
api/app/seed.py; the API also runs it at start-up, so this script is only
needed locally or to reset config.

Run:  python scripts/seed_db.py [--reset-config]
      python scripts/seed_db.py --print-schema   # regenerate api/schema.sql
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "api"))

from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateTable  # noqa: E402

from app import db  # noqa: E402
from app.seed import seed  # noqa: E402,F401  (re-exported for tests and mock/make_fixtures.py)


def print_schema() -> None:
    parts = ["-- Generated from api/app/db.py by `python scripts/seed_db.py --print-schema`.",
             "-- Postgres dialect. The app creates the same tables on SQLite with metadata.create_all().", ""]
    for table in db.metadata.sorted_tables:
        parts.append(str(CreateTable(table).compile(dialect=postgresql.dialect())).strip() + ";\n")
    (REPO / "api" / "schema.sql").write_text("\n".join(parts), encoding="utf-8")
    print("wrote api/schema.sql")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print-schema", action="store_true")
    ap.add_argument("--reset-config", action="store_true")
    args = ap.parse_args()
    if args.print_schema:
        print_schema()
    else:
        seed(args.reset_config)


if __name__ == "__main__":
    main()
