# AduthaBus Lite

AI-assisted bus reallocation for a Chennai (Tamil Nadu) route cluster: forecast demand, detect
overcrowded / underused / delayed / bunched routes, and recommend moving buses
between routes with an explained, human-approved card. Zero budget, hosted on
Render's free tier.

- Problem and constraints: [`.data/`](.data/)
- Design: [`.reports/solutions/solution2.md`](.reports/solutions/solution2.md)
- Shared API contract (source of truth for every JSON shape): [`.reports/implementation/00-shared-contract.md`](.reports/implementation/00-shared-contract.md)
- Backend plan: [`01-backend-plan.md`](.reports/implementation/01-backend-plan.md) · Frontend plan: [`02-frontend-plan.md`](.reports/implementation/02-frontend-plan.md)

## Repository layout

| Path | What |
|---|---|
| `api/` | FastAPI service (the one Render web service). `app/core/` = forecast, detection, optimiser, replay; `app/sim/` = SimPy simulator; `app/routers/` = endpoints |
| `offline/` | Laptop-only lane: data prep, model training, batch simulation |
| `data/artefacts/` | Committed outputs the API loads at start-up (8.2 MB) |
| `mock/` | Fixtures for every endpoint + mock server for frontend work |
| `scripts/` | `seed_db.py`, `export_log.py`, `toy_load_test.py` |
| `render.yaml` | Render Blueprint (API + Postgres + 3 static sites) |

## Quick start (backend)

Python 3.12 or newer.

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows; use `source .venv/bin/activate` elsewhere
pip install -r api/requirements-dev.txt
cp .env.example .env              # local passwords and JWT secret; never commit .env
python scripts/seed_db.py         # creates SQLite tables + operator/admin users
cd api && uvicorn app.main:app --reload --port 8001
```

Log in with `operator` / the `OPERATOR_PASSWORD` from `.env`. Demo flow:

```bash
POST /clock  {"action":"jump","scenario":"event_surge","t":"2026-09-25T17:15:00+05:30"}
POST /cycle                     # -> "Move 1 bus from Route 9M to Route 3 ..." card
POST /whatif {"recommendation_id":"rec_0001"}
POST /decisions {"recommendation_id":"rec_0001","decision":"approve"}
GET  /state                     # moved bus now runs on Route 3
```

Tests: `cd api && python -m pytest -q` (68 tests: unit, contract vs fixtures, integration, mock server).

## Mock server (for Person B, from day 1)

```bash
pip install fastapi uvicorn
uvicorn mock.server:app --port 8000      # run from the repo root
```

Serves [`mock/fixtures/`](mock/fixtures/) on the real paths. Any username logs in
(`admin` gets the admin role, anything else operator). `/whatif` waits 3 s.
Buses in `/state` and `/buses` move along the route shapes as the clock
advances. Fixtures are generated from the real API
(`python mock/make_fixtures.py`), so their shapes match it exactly;
`api/tests/test_contract.py` fails if they drift.

Fixture files: `health`, `auth_login`, `auth_device`, `clock`, `state`,
`routes`, `buses`, `eta`, `cycle`, `recommendations`, `decisions_post`,
`decisions` (+ `decisions.csv`), `whatif`, `results`, `alerts`, `crowding`,
`admin_routes`, `admin_fleet`.

## Offline lane (rebuild all artefacts)

```bash
pip install -r offline/requirements.txt
python offline/run_all.py          # ~5 min: network, weather, ETM, segments, replay, models, batch, fixtures
```

| Step | Script | Output |
|---|---|---|
| Route cluster | `offline/data_prep/gtfs_subset.py` (downloads the Chennai GTFS to `data/raw/` if missing; routes in [`cluster.yaml`](offline/data_prep/cluster.yaml)) | `gtfs/*.parquet`, `config.json` |
| Weather | `weather.py` (Open-Meteo archive, synthetic fallback) | `history/weather.parquet` |
| Boardings | `synthetic_etm.py` (formula in `demand_params.yaml`) | `history/boardings.parquet` |
| Running times | `derive.py` (synthetic) or `derive.py --real <dates>` after `record_rt.py` + `clean_rt.py` | `history/segments.parquet` |
| Replay days | `build_replay.py` + `load_estimation.py` (IPF) | `replay/<scenario>/` |
| Models | `offline/models/train.py` | `models/*.txt`, [`offline/models/metrics.md`](offline/models/metrics.md) |
| Batch results | `offline/sim/run_batch.py` | `results.json` |

### What is real and what is synthetic

| Input | Status |
|---|---|
| Weather | Real (Open-Meteo archive, Chennai, Jul–Sep 2026) |
| Route cluster | Real stops and stop order for 5 Chennai MTC routes (3, 9M, 5E, 78, S13; 101 stops) from the community [ChennaiGTFS](https://github.com/ungalsoththu/ChennaiGTFS) feed by UngalSoththu (ODbL, collected from the MTC app, not an official release). Headways, busy factors, depots and stop types are set by hand in [`cluster.yaml`](offline/data_prep/cluster.yaml). Route shapes are straight lines between stops (the feed has no shapes) |
| Bus positions / running times | Synthetic until ≥ 3 weekdays + 1 weekend of GTFS-RT are recorded (`record_rt.py` needs a `GTFS_RT_URL` and `GTFS_RT_KEY`; Chennai MTC has no public GTFS-RT feed yet) |
| Boardings (ETM) | Synthetic by design (no open ETM data), calibrated to about 1,000 passengers per bus per day (MTC: about 32 lakh riders on about 3,230 services); rider crowding reports are the real signal |
| Holidays | [`holidays.csv`](offline/data_prep/holidays.csv), hand-entered; check against the official 2026 list |

Replay days are generated by the simulator's baseline strategy, so the API
shows load *estimates* from boardings + IPF (MAE 3–4 passengers vs the
simulator's true load), never the true load.

## Results so far (offline batch, 16:30–19:30, 5 seeds)

From [`data/artefacts/results.json`](data/artefacts/results.json):

| Scenario | Strategy | Avg wait | Overload min | Left behind | Bunching | Deadhead km |
|---|---|---|---|---|---|---|
| Event surge | Baseline | 5.74 | 458 | 347 | 119 | 0 |
| Event surge | Holding | 5.72 | 452 | 387 | 99 | 0 |
| Event surge | AduthaBus (no forecast error) | 5.55 | 348 | 172 | 123 | 2.2 |
| Event surge | AduthaBus (missed surge) | 5.50 | 373 | 167 | 34 | 0 |
| Normal weekday | Baseline | 5.47 | 94 | 2 | 68 | 0 |
| Normal weekday | Holding | 5.48 | 110 | 8 | 63 | 0 |
| Normal weekday | AduthaBus | 5.40 | 58 | 2 | 17 | 0 |

Read honestly: in the surge, AduthaBus cuts overload minutes by 24% and
left-behind passengers by half against the baseline, and average wait by 3%;
bunching does not improve. When the forecast misses the surge it moves no
buses (0 deadhead km) yet still cuts overload by 19%, so most of that gain
comes from headway-based dispatching, not reallocation. On a normal day it makes no moves and cuts
overload and bunching through dispatching alone. All inputs except weather
and the route network are synthetic.

## Deployment (Render free)

1. Push to GitHub, then in Render: **New → Blueprint** and pick this repo (`render.yaml`).
2. Set `OPERATOR_PASSWORD` and `ADMIN_PASSWORD` in the dashboard (marked `sync: false`).
3. Start command runs Uvicorn only. The API's start-up thread seeds the database (`api/app/seed.py`: creates tables, resets demo passwords from env), so the port opens at once.
4. After each deploy: `curl https://aduthabus-api.onrender.com/health` and one `/state` call.
5. Free Postgres expires 30 days after creation: run `DATABASE_URL=<external url> python scripts/export_log.py` before then; recreate with `api/schema.sql` + `seed_db.py`.

Memory and timing (`python scripts/toy_load_test.py`):

| Where | Import libs | API start-up | RSS after /state + /cycle + /whatif | /cycle | /whatif |
|---|---|---|---|---|---|
| Laptop (Windows, Python 3.14) | 1.3 s | 1.9 s | 210 MB | 0.12 s | 0.43 s |
| Render free (0.1 CPU, 512 MB) | _to record after first deploy_ | | | | |

## Deviations from the plans (for review)

| Plan item | What was done | Why |
|---|---|---|
| Python 3.11 | Python 3.12 on Render (`PYTHON_VERSION`) | numpy 2.5 needs ≥ 3.12 |
| passlib[bcrypt] | `bcrypt` directly | passlib 1.7.4 breaks with bcrypt 5 |
| gtfs-kit | plain Polars CSV reading in `gtfs_subset.py` | avoids GeoPandas in the offline stack |
| Contract §11 API root `api` | no `rootDir`; build/start commands `cd api` | the API reads `data/artefacts/`, which is outside `api/` |
| Strategy 3 "holding + reallocation" | headway-based holding + reallocation | schedule-based holding cannot absorb a bus added mid-day; see `api/app/sim/strategies.py` |
| `decided_at` | replay time (same clock as `created_at`); wall time kept in DB column `decided_wall_at` | consistent timeline on the console |
| Optional live mode, LLM rewording (B7.3–B7.4) | not built | optional; replay mode is the demo |

## Handoff to Person B

- Mock server: `uvicorn mock.server:app --port 8000` (fixture list above).
- Demo users: `operator`, `admin`. Passwords are shared privately, never in Git.
- Card that reliably appears: scenario `event_surge`, jump to `17:10`–`17:15`, `POST /cycle`.
- Scenario names for the clock dropdown: `normal_weekday`, `heavy_rain`, `event_surge`, `breakdown`.
- Clock state lives in API memory: re-read `GET /clock` after a `503` or reconnect. A `jump` with a `scenario` (or without `t`) resets approved fleet changes and expires open cards.
- Admin: new routes are stored and listed, but only routes in the replay network get buses and recommendations; `min_headway_min` and depot fleet edits feed the optimiser immediately.
