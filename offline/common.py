"""Shared helpers for offline scripts: paths and access to the API package so
training, simulation and inference use the same code (plan B2.1)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
API_DIR = REPO / "api"
ARTEFACTS = REPO / "data" / "artefacts"
DATA_PREP = REPO / "offline" / "data_prep"
RAW = REPO / "data" / "raw"          # git-ignored: GTFS zips, RT recordings

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))


def load_yaml(path: Path) -> dict:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))
