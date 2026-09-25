"""TransitPulse Lite API (FastAPI, one process, Render free web service).

Start-up loads the network, models and replay days in a background thread so
`/health` answers at once. Until loading finishes every other endpoint returns
503 with code "loading" (contract §6 notes).
"""
from __future__ import annotations

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db, errors
from .config import settings
from .routers import admin, auth, clock, cycle, decisions, public, rider, whatif
from .routers import state as state_router
from .schemas import HealthOut
from .service import state


def rss_mb() -> float | None:
    """Resident memory in MB (Linux /proc; None elsewhere)."""
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        return None
    return None


def _load() -> None:
    state.load()
    print(f"start-up: ready={state.ready} in {state.load_seconds}s, models_loaded={state.models_loaded}, "
          f"rss_mb={rss_mb()}, error={state.error}", flush=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=_load, name="loader", daemon=True).start()
    yield


app = FastAPI(title="TransitPulse Lite API", version=settings.version, lifespan=lifespan)
errors.install(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.middleware("http")
async def loading_gate(request: Request, call_next):
    if request.url.path != "/health" and request.method != "OPTIONS" and not state.ready:
        msg = "server is starting, try again shortly" if state.error is None else f"start-up failed: {state.error}"
        return JSONResponse(errors.error_body("loading", msg), status_code=503, headers={"Retry-After": "5"})
    return await call_next(request)


@app.get("/health", response_model=HealthOut, tags=["health"])
def health() -> dict:
    return {"status": "ok" if state.ready else "loading", "models_loaded": state.models_loaded,
            "db": "ok" if db.ping() else "down", "version": settings.version}


for r in (auth.router, clock.router, state_router.router, public.router, cycle.router, decisions.router,
          whatif.router, rider.router, admin.router):
    app.include_router(r)
