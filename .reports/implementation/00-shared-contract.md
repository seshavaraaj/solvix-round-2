# TransitPulse Lite — Shared Contract (Backend ↔ Frontend)

| Field | Value |
|---|---|
| Drafted | 2026-09-25 |
| Based on | [`../solutions/solution2.md`](../solutions/solution2.md) |
| Owners | Both people. Person A (backend) and Person B (frontend). |
| Read with | [`01-backend-plan.md`](01-backend-plan.md) (Person A), [`02-frontend-plan.md`](02-frontend-plan.md) (Person B) |

This file is the single source of truth for everything the two halves share: repo layout, API endpoints, JSON shapes, auth, environment variables, milestones, and deployment. The two person plans link here and never copy schemas.

**Change rule:** Any change to an endpoint, field, or milestone is a pull request that edits this file. The other person must approve it before either side codes against the change.

---

## 1. Roles

| Person | Owns | Does not touch |
|---|---|---|
| **A — Backend** | `offline/`, `api/`, `mock/`, `data/artefacts/`, `scripts/`, `render.yaml`, Render API + DB services | UI code |
| **B — Frontend** | `operator/`, `admin/`, `rider/`, Render static sites (build settings) | Server logic, models |

Shared: this file, `README.md`, `.github/` (if CI is added).

## 2. Repository layout (monorepo)

```
solvix-round-2/
├─ .reports/implementation/   # these plans
├─ offline/                   # A: data prep, training, sim batch (runs on laptops)
│  ├─ data_prep/  models/  sim/
├─ data/artefacts/            # A: committed outputs (Parquet, model .txt, results.json) — keep < 100 MB
├─ api/                       # A: FastAPI service
│  ├─ app/  (main.py, routers/, core/, sim/, templates/)
│  ├─ schema.sql
│  └─ requirements.txt
├─ mock/                      # A writes, B consumes: fixtures + mock server
│  ├─ fixtures/*.json
│  └─ server.py
├─ scripts/                   # A: export_log.py, seed_db.py
├─ operator/                  # B: React + Vite + TS (operator console)
├─ admin/                     # B: React + Vite + TS (fleet admin portal)
├─ rider/                     # B: Flutter (Web target, optional APK)
└─ render.yaml                # A owns; B supplies static-site build commands
```

## 3. Conventions

| Topic | Rule |
|---|---|
| Base URL | `API_URL` env var in every frontend (see Section 8). No hard-coded hosts. |
| Format | JSON, UTF-8, `snake_case` field names. |
| IDs | Strings (`"534"`, `"bus_DL1PC1234"`, `"rec_0017"`). |
| Time | ISO-8601 with offset, Asia/Kolkata: `"2026-09-25T17:30:00+05:30"`. Replay time `t` uses the same format. |
| Coordinates | `lat`, `lon` as decimal degrees (WGS84). Shapes as GeoJSON `LineString` (`[lon, lat]` order, per GeoJSON spec). |
| Load factor | Float, `1.0` = 100% of rated capacity. |
| Errors | HTTP status + body `{"error": {"code": "string", "message": "string"}}`. |
| Status codes | `200` OK, `201` created, `400` bad input, `401` no/invalid token, `403` wrong role, `404` not found, `409` conflict (e.g. recommendation already decided), `429` rate limited, `503` server still loading models. |
| Auth header | `Authorization: Bearer <jwt>` |
| CORS | API allows origins in `CORS_ORIGINS` (3 static-site URLs + `http://localhost:5173`, `:5174`, `:8080`). |
| Versioning | No URL version prefix for the hackathon. Breaking changes follow the change rule above. |

## 4. Authentication

Self-rolled JWT (FastAPI + passlib + PyJWT). No paid identity vendor.

| Role | How the token is obtained | Used by |
|---|---|---|
| `operator` | `POST /auth/login` with username + password | Operator console |
| `admin` | `POST /auth/login` with username + password | Fleet admin portal |
| `rider` | `POST /auth/device` with an anonymous device UUID | Rider app (only for `POST /crowding`) |

JWT claims: `{"sub": "string", "role": "operator|admin|rider", "exp": <unix seconds>}`. Lifetime: 12 h for operator/admin, 30 days for rider.

Demo accounts are seeded by `scripts/seed_db.py`: `operator / <from env>`, `admin / <from env>`. Passwords live in Render env vars, never in Git.

Public endpoints (no token): `/health`, `/routes`, `/buses`, `/alerts`, `/results`, `/auth/*`.

## 5. Shared data types

Frontend mirrors these as TypeScript interfaces (`operator/src/api/types.ts`, `admin/src/api/types.ts`) and Dart classes (`rider/lib/api/models.dart`). Backend defines them as Pydantic models in `api/app/schemas.py`. Field names must match exactly.

### Route
```json
{
  "id": "534",
  "name": "534 Anand Vihar ISBT – Nehru Place",
  "depot_id": "depot_okhla",
  "color": "#E4572E",
  "min_headway_min": 15,
  "shape": {"type": "LineString", "coordinates": [[77.315, 28.646], [77.251, 28.549]]},
  "stops": [{"id": "stop_1021", "name": "Nehru Place", "lat": 28.5494, "lon": 77.2517, "seq": 14}]
}
```

### Bus
```json
{
  "id": "bus_DL1PC1234",
  "route_id": "534",
  "direction": 0,
  "lat": 28.561,
  "lon": 77.262,
  "bearing": 210,
  "load_factor": 1.18,
  "delay_min": 6.5,
  "dark": false,
  "last_seen": "2026-09-25T17:29:40+05:30"
}
```
`dark` = no position report for more than 2 minutes.

### RouteHealth
```json
{
  "route_id": "534",
  "direction": 0,
  "flags": {
    "overcrowded": {"on": true, "confidence": "high", "evidence": "P90 load 1.25 at Nehru Place, 17:30–18:30"},
    "underused":   {"on": false, "confidence": "high", "evidence": null},
    "delay_emerging": {"on": false, "confidence": "medium", "evidence": null},
    "bunching":    {"on": true, "confidence": "low", "evidence": "Headway 4 min vs planned 10 min; 1 dark bus"}
  }
}
```
`confidence` ∈ `"high" | "medium" | "low"`.

### FeedHealth
```json
{"buses_expected": 42, "buses_reporting": 38, "share_reporting": 0.905, "mode": "replay", "fresh": true}
```
`mode` ∈ `"replay" | "live"`.

### Recommendation
```json
{
  "id": "rec_0017",
  "created_at": "2026-09-25T17:15:00+05:30",
  "action": "move_bus",
  "from_route_id": "423",
  "to_route_id": "534",
  "bus_count": 2,
  "window_start": "2026-09-25T17:30:00+05:30",
  "window_end": "2026-09-25T19:00:00+05:30",
  "trigger_flags": ["overcrowded"],
  "expected_effect": {
    "to_route":   {"wait_min_before": 11.0, "wait_min_after": 7.0, "peak_load_before": 1.25, "peak_load_after": 0.92},
    "from_route": {"wait_min_before": 7.5,  "wait_min_after": 9.0, "peak_load_before": 0.28, "peak_load_after": 0.41}
  },
  "deadhead_km": 6.0,
  "confidence": "high",
  "explanation": "Move 2 buses from Route 423 to Route 534, 17:30–19:00. ...",
  "status": "pending",
  "solver": "cp_sat"
}
```
- `action` ∈ `"move_bus" | "add_trip" | "release_bus"`.
  - `move_bus`: `from_route_id` and `to_route_id` set.
  - `add_trip`: `from_route_id` = `null` (depot reserve), `to_route_id` set.
  - `release_bus`: `from_route_id` set, `to_route_id` = `null` (to depot).
- `status` ∈ `"pending" | "approved" | "rejected" | "expired"`.
- `solver` ∈ `"cp_sat" | "greedy"`.

### Decision
```json
{"recommendation_id": "rec_0017", "decision": "reject", "reason": "no_driver", "note": "Driver shift ends 18:00", "decided_by": "operator", "decided_at": "2026-09-25T17:16:10+05:30"}
```
- `decision` ∈ `"approve" | "reject"`.
- `reason` (required on reject) ∈ `"no_driver" | "bus_unavailable" | "local_knowledge" | "forecast_wrong" | "other"`.

### WhatIfResult
```json
{
  "recommendation_id": "rec_0017",
  "horizon_min": 120,
  "runtime_s": 6.2,
  "without": {"avg_wait_min": 10.8, "p95_wait_min": 21.0, "left_behind": 140, "overload_min": 55, "bunching_events": 4},
  "with":    {"avg_wait_min": 7.1,  "p95_wait_min": 13.5, "left_behind": 22,  "overload_min": 8,  "bunching_events": 2},
  "series": [{"t": "2026-09-25T17:30:00+05:30", "load_without": 1.1, "load_with": 0.9}]
}
```

### ScenarioResult (from `GET /results`)
```json
{
  "scenarios": ["normal_weekday", "heavy_rain", "event_surge", "breakdown"],
  "strategies": ["baseline", "holding", "transitpulse"],
  "error_levels": [0, 0.2, 0.4, "missed_surge"],
  "rows": [
    {"scenario": "event_surge", "strategy": "transitpulse", "error_level": 0,
     "avg_wait_min": 7.9, "p95_wait_min": 15.2, "left_behind": 60, "overload_min": 20,
     "bunching_events": 5, "avg_load_factor": 0.71, "deadhead_km": 18.0, "changes_per_hour": 1.2}
  ]
}
```

### Alert (rider-facing)
```json
{"id": "al_03", "route_id": "534", "kind": "delay", "message": "Route 534 running about 8 minutes late near Nehru Place.", "since": "2026-09-25T17:20:00+05:30"}
```
`kind` ∈ `"delay" | "bunching" | "crowded" | "service_change"`. `service_change` is emitted when an approved recommendation changes a route.

### CrowdingReport
```json
{"bus_id": "bus_DL1PC1234", "route_id": "534", "level": "crowded", "lat": 28.561, "lon": 77.262}
```
`level` ∈ `"crowded" | "ok" | "empty"`. Server adds `device_id` (from token) and `received_at`.

### Fleet config (admin)
```json
{"depot_id": "depot_okhla", "name": "Okhla Depot", "lat": 28.53, "lon": 77.27, "fleet_size": 60, "reserve": 4, "out_of_service": 1}
```

## 6. Endpoints

| # | Method + path | Auth | Request | Response | Milestone | Producer (A) phase | Consumer (B) phase |
|---|---|---|---|---|---|---|---|
| 1 | `GET /health` | none | — | `{"status":"ok"\|"loading","models_loaded":bool,"db":"ok"\|"down","version":"sha"}` | M0 | B0 | F1, F5 |
| 2 | `POST /auth/login` | none | `{"username","password"}` | `{"token","role","expires_at"}` | M1 | B3 | F1, F6 |
| 3 | `POST /auth/device` | none | `{"device_id":"uuid"}` | `{"token","role":"rider","expires_at"}` | M4 | B6 | F5 |
| 4 | `GET /clock` | operator | — | `{"t","speed":1\|10\|30,"playing":bool,"scenario"}` | M1 | B3 | F1 |
| 5 | `POST /clock` | operator | `{"action":"play"\|"pause"\|"jump","speed"?, "scenario"?, "t"?}` | same as `GET /clock` | M1 | B3 | F1 |
| 6 | `GET /state?t=` | operator | `t` optional (default = clock) | `{"t","buses":[Bus],"route_health":[RouteHealth],"feed":FeedHealth}` | M1 | B3 (+B2 flags) | F2 |
| 7 | `GET /routes` | none | — | `[Route]` | M1 | B3 | F2, F5, F6 |
| 8 | `GET /buses?route_id=&t=` | none | filters optional | `[Bus]` (no `load_factor` detail beyond value) | M1 | B3 | F5 |
| 9 | `GET /eta?stop_id=&route_id=` | none | — | `[{"bus_id","route_id","eta_min","load_factor"}]` | M1 | B3 | F5 |
| 10 | `POST /cycle?t=` | operator | — | `{"t","ran":bool,"recommendations":[Recommendation]}`; `ran=false` if last cycle < 15 simulated min old (returns cached list) | M2 | B4 | F3 |
| 11 | `GET /recommendations?status=` | operator | — | `[Recommendation]` | M2 | B4 | F3 |
| 12 | `POST /decisions` | operator | `Decision` (without `decided_by`, `decided_at`) | `Decision` (201); `409` if already decided | M2 | B4 | F3 |
| 13 | `GET /decisions` | operator, admin | `?limit=&offset=` | `[Decision]` | M2 | B4 | F6 |
| 14 | `GET /decisions.csv` | operator, admin | — | `text/csv` download | M2 | B4 | F3, F6 |
| 15 | `POST /whatif` | operator | `{"recommendation_id"}` | `WhatIfResult`; may take up to 10 s | M3 | B5 | F4 |
| 16 | `GET /results` | none | — | `ScenarioResult` | M3 | B5 | F4 |
| 17 | `GET /alerts?route_id=` | none | — | `[Alert]` | M4 | B6 | F5 |
| 18 | `POST /crowding` | rider | `CrowdingReport` | `201 {"accepted":true}`; `429` if > 1 report per bus per 5 min per device | M4 | B6 | F5 |
| 19 | `GET /admin/routes` | admin | — | `[Route]` | M4 | B6 | F6 |
| 20 | `POST /admin/routes` | admin | `Route` | `Route` (201) | M4 | B6 | F6 |
| 21 | `PUT /admin/routes/{id}` | admin | `Route` | `Route` | M4 | B6 | F6 |
| 22 | `GET /admin/fleet` | admin | — | `[Fleet config]` | M4 | B6 | F6 |
| 23 | `PUT /admin/fleet/{depot_id}` | admin | `Fleet config` | `Fleet config` | M4 | B6 | F6 |

Notes:
- Endpoints 4, 5, 9, 11, 13, 17 extend the table in solution2 §6.8. They are needed by the UIs described in solution2 §6.10.
- Cold start: while models load, every endpoint except `/health` returns `503` with code `"loading"`. Frontends show the wake-up screen until `/health` returns `"status":"ok"`.
- The replay clock state lives in API memory. If the service restarts, the clock resets to the scenario start. Frontends must re-read `GET /clock` after a `503` or reconnect.

## 7. Mock server (unblocks Person B from day 1)

- Person A creates `mock/fixtures/` with one JSON file per endpoint, using the examples in Section 5 expanded to realistic sizes (4–6 routes, ~40 buses).
- `mock/server.py`: a tiny FastAPI app that serves the fixtures on the same paths, accepts any login, and fakes `/whatif` with a 3-second delay. Run with `uvicorn mock.server:app --port 8000`.
- Buses in `/state` move along route shapes as `t` advances, so the map animates.
- Person B points `API_URL` at `http://localhost:8000` until the real milestone lands, then switches to the real API (local or Render). No UI code changes.
- Rule: when a schema in Section 5 changes, the same PR updates the fixture.

## 8. Environment variables

| Variable | Where | Example | Set by |
|---|---|---|---|
| `DATABASE_URL` | API | from Render DB (`fromDatabase`) | A |
| `JWT_SECRET` | API | Render `generateValue: true` | A |
| `CORS_ORIGINS` | API | comma-separated static-site URLs | A |
| `OPERATOR_PASSWORD`, `ADMIN_PASSWORD` | API (seed) | set in Render dashboard | A |
| `LIVE_MODE` | API | `false` (default) | A |
| `GTFS_RT_KEY` | API (live mode only) | Delhi OTD key | A |
| `VITE_API_URL` | operator, admin (build time) | `https://transitpulse-api.onrender.com` | B |
| `API_URL` | rider (`--dart-define=API_URL=...` at build) | same | B |

## 9. Milestones and sync points

Both plans use these IDs. A milestone is **done** only when the endpoints are live on the Render API URL **and** the consumer has confirmed the frontend works against them.

| ID | Name | Backend (A) delivers | Frontend (B) delivers | Sync action |
|---|---|---|---|---|
| **M0** | Skeleton | Repo layout; `mock/` server + all fixtures; `/health` deployed on Render; `render.yaml` draft; memory + cold-start numbers | Three app skeletons build locally against mock; wake-up screen; build commands for `render.yaml` | 30-min call: walk through this file, freeze Sections 5–6 v1 |
| **M1** | Live map | `/auth/login`, `/clock`, `/state`, `/routes`, `/buses`, `/eta` on real replay data | Operator map + clock + route table on real API; rider map on real API | Joint test: play replay at ×30, buses move on both apps |
| **M2** | Recommendations | `/cycle`, `/recommendations`, `/decisions`, CSV | Recommendation queue, approve/reject, CSV button | Joint test: event-surge scenario produces a card; approve writes to Postgres |
| **M3** | Proof | `/whatif` (< 10 s on Render), `/results` with full batch | What-if panel + Results tab | Joint test: what-if on Render finishes; results charts match `results.json` |
| **M4** | Rider + admin | `/auth/device`, `/crowding`, `/alerts`, `/admin/*` | Rider crowding + alerts; admin forms | Joint test: rider "Crowded" report raises load on the operator map |
| **M5** | Demo ready | Hardening, export script, robustness results | Polish, mobile checks | Full rehearsal of solution2 §11 demo script on Render URLs |

Parallel lanes (A and B work at the same time):

```
A: B0 ── B1 ── B2 ── B3 ──► M1 ── B4 ──► M2 ── B5 ──► M3 ── B6 ──► M4 ── B7 ──► M5
B: F0 ─(mock)─ F1 ─────────► M1 ── F2 ── F3 ──► M2 ── F4 ──► M3 ── F5 ── F6 ──► M4 ── F7 ──► M5
```
B builds every screen against the mock first, so B never waits on A. At each milestone B only swaps `API_URL` and fixes gaps.

**Cut order if time runs short** (from solution2 §10): admin portal (F6/B6 admin CRUD → seed JSON) first, then rider app. Operator console and M0–M3 are required.

## 10. Git workflow

- `main` is always deployable. Render auto-deploys from `main`.
- Branches: `be/<topic>` for A, `fe/<topic>` for B, `contract/<topic>` for edits to this file.
- PRs that touch this file or `mock/fixtures/` need approval from the other person.
- Commit artefacts in `data/artefacts/` only through A. Keep the folder under 100 MB.
- Tag each milestone: `m0`, `m1`, … so either person can roll back.

## 11. Render deployment map

All in one `render.yaml` Blueprint. A owns the file; B supplies the static-site entries.

| Service | Type (free) | Root | Build command | Publish dir / start | Owner |
|---|---|---|---|---|---|
| `transitpulse-api` | Web service, Python | `api` | `pip install -r requirements.txt` | `uvicorn app.main:app --host 0.0.0.0 --port $PORT`; health check `/health` | A |
| `transitpulse-db` | Postgres | — | — | `DATABASE_URL` → API | A |
| `transitpulse-operator` | Static site | `operator` | `npm ci && npm run build` | `dist`; rewrite `/*` → `/index.html` | B |
| `transitpulse-admin` | Static site | `admin` | `npm ci && npm run build` | `dist`; rewrite `/*` → `/index.html` | B |
| `transitpulse-rider` | Static site | `rider` | see [`02-frontend-plan.md#f5`](02-frontend-plan.md#f5--rider-app-flutter) (Flutter SDK is not preinstalled on Render) | `build/web` | B |

Free-tier rules (from [`../../.data/constraints.md`](../../.data/constraints.md)): one web service, one database, static sites free. Free web service sleeps after 15 min idle (≈1 min cold start). Free Postgres expires 30 days after creation, so A runs `scripts/export_log.py` before expiry.

## 12. Definition of done (both people)

- Endpoint exists on Render, matches Section 5–6 shapes, and is consumed by at least one frontend screen.
- No secrets in Git.
- No paid service, key with billing, or non-Render cloud host introduced. If one seems needed, raise it in a `contract/` PR first.
