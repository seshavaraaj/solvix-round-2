"""Settings read from environment variables (contract §8)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = API_DIR.parent


def _load_dotenv() -> None:
    """Read a local .env (repo root or api/) without adding a dependency."""
    for path in (REPO_DIR / ".env", API_DIR / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", f"sqlite:///{REPO_DIR / 'aduthabus.db'}")
    # Render gives postgres://...; SQLAlchemy + psycopg 3 wants postgresql+psycopg://
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=_database_url)
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", "dev-secret-change-me"))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in os.getenv(
                "CORS_ORIGINS",
                "http://localhost:5173,http://localhost:5174,http://localhost:8080",
            ).split(",")
            if o.strip()
        )
    )
    operator_password: str | None = field(default_factory=lambda: os.getenv("OPERATOR_PASSWORD"))
    admin_password: str | None = field(default_factory=lambda: os.getenv("ADMIN_PASSWORD"))
    live_mode: bool = field(default_factory=lambda: _bool("LIVE_MODE"))
    gtfs_rt_key: str | None = field(default_factory=lambda: os.getenv("GTFS_RT_KEY") or None)
    gtfs_rt_url: str = field(
        default_factory=lambda: os.getenv("GTFS_RT_URL", "")
    )
    artefacts_dir: Path = field(
        default_factory=lambda: Path(os.getenv("ARTEFACTS_DIR", str(REPO_DIR / "data" / "artefacts")))
    )
    version: str = field(
        default_factory=lambda: (os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_SHA") or "dev")[:7]
    )
    # Scenario the clock starts on after a restart.
    default_scenario: str = field(default_factory=lambda: os.getenv("DEFAULT_SCENARIO", "event_surge"))


settings = Settings()
