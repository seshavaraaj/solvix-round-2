# AduthaBus Lite — Backend Implementation Plan (Person A)

| Field | Value |
|---|---|
| Drafted | 2026-09-25 |
| Owner | Person A — Backend |
| Scope | Offline data + AI lane, FastAPI service, Postgres, simulator, mock server, `render.yaml` |
| Contract | [`00-shared-contract.md`](00-shared-contract.md) — all JSON shapes and endpoints live there |
| Partner plan | [`02-frontend-plan.md`](02-frontend-plan.md) (Person B) |
| Source design | [`../solutions/solution2.md`](../solutions/solution2.md) §5–§8, §10–§12 |

**Rule:** do not change a response shape without a `contract/` PR (see contract §10). If code and contract disagree, the contract wins until the PR is merged.

---

## Stack (all free / open source, pin versions in `api/requirements.txt`)

| Layer | Choice |
|---|---|
| Language | Python 3.11 |
| API | FastAPI, Uvicorn, Pydantic v2 |
| Auth | PyJWT, passlib[bcrypt] |
| Data | Polars (preferred for RAM) or pandas, PyArrow, DuckDB |
| GTFS | `gtfs-kit`, `gtfs-realtime-bindings` |
| Forecast | LightGBM (quantile objective) |
| Optimiser | OR-Tools CP-SAT |
| Simulator | SimPy |
| Explanations | Jinja2 |
| DB | SQLAlchemy 2 + `psycopg[binary]`; SQLite locally |
| Tests | pytest, httpx `TestClient`, `jsonschema` |

Offline-only libraries (training, map-matching) go in `offline/requirements.txt`, **not** in `api/requirements.txt`, to keep the Render image small.

---

## Phase B0 — Validation and skeleton → unblocks **M0**

Goal: prove the stack fits Render free (512 MB, 0.1 CPU) and give Person B a mock API on day 1.

Tasks
1. Create repo layout from contract §2. Add `README.md` with how to run each part.
2. Write `mock/fixtures/*.json` for **every** endpoint in contract §6 (4–6 routes, ~40 buses). Write `mock/server.py` (contract §7): serves fixtures, accepts any login, moves buses along shapes as `t` advances, delays `/whatif` by 3 s.
3. `api/app/main.py` with `GET /health`, CORS from `CORS_ORIGINS`, a `503 loading` middleware while start-up loads artefacts.
4. Toy load test: import LightGBM + OR-Tools + Polars, load one dummy model, solve one toy CP-SAT model. Log RSS memory and start time.
5. Draft `render.yaml` (contract §11) with API + DB. Add Person B's static-site entries when received.
6. Deploy to Render free. Record: idle RAM, peak RAM during toy solve, cold-start seconds. Put the numbers in `README.md`.

Done when: mock server runs locally; `/health` answers on the Render URL; memory numbers recorded (target ≤ 350 MB idle, see solution2 §6.8 budget).

Handoff to B: mock server command, Render API URL, fixture file list.

---

## Phase B1 — Data (offline lane, laptop)

Files: `offline/data_prep/`

1. **Pick cluster** (solution2 §13 Q1): 4–6 Delhi routes sharing a corridor and 1–2 depots, with at least one busy and one quiet route.
2. `gtfs_subset.py`: filter Delhi OTD static GTFS to the cluster → `data/artefacts/gtfs/*.parquet` (routes, stops, shapes, trips, stop_times).
3. `record_rt.py`: poll Delhi OTD GTFS-RT every 30 s, save one row per position to Parquet. Record ≥ 3 weekdays + 1 weekend day. Key in local `.env`, never committed.
4. `clean_rt.py`: map-match to shapes, drop points > 50 m off route, mark `dark` after 2 min silence.
5. `derive.py`: segment running times, headways, delays → Parquet.
6. `synthetic_etm.py` (solution2 §6.3): base rate × time-of-day × day-type × weather × event; calibrate to published DTC daily totals; parameters in a YAML file; accepts real ETM in same schema.
7. `weather.py`: Open-Meteo hourly history for recorded days. `holidays.csv` by hand.
8. `load_estimation.py` (solution2 §6.2): alighting assignment + IPF → load factor per trip-segment.
9. Build **replay day files**: one Parquet per scenario day for the API, small enough to hold a 2-hour window in memory.

Done when: `data/artefacts/` has GTFS subset, cleaned replay days, synthetic boardings, load estimates; total < 100 MB.

---

## Phase B2 — Forecast and detection

Files: `offline/models/`, `api/app/core/forecast.py`, `api/app/core/detect.py`

1. Feature builder shared by training and inference (`api/app/core/features.py`, imported by offline scripts so both lanes use the same code).
2. Train LightGBM demand model: quantile P50 and P90, target = boardings per route-direction-stop group-15 min band. Sample weights on high-load rows.
3. Train LightGBM travel-time model per segment.
4. Save as LightGBM text files in `data/artefacts/models/`. Record MAE / pinball loss in `offline/models/metrics.md`.
5. `forecast.py`: load models once at start-up; `predict(window)` returns P50/P90 load factor per route-segment-band.
6. `detect.py`: the four flags from solution2 §6.5, with `evidence` string and `confidence` exactly as `RouteHealth` in contract §5. Lower confidence when a dark bus is involved.

Done when: unit tests show each flag fires on a hand-made case; models load in the API in < 20 s on Render.

---

## Phase B3 — API core → unblocks **M1**

Files: `api/app/routers/{auth,clock,state,public}.py`, `api/app/core/replay.py`, `api/app/db.py`, `api/schema.sql`

1. `schema.sql`: tables `users`, `recommendations`, `decisions`, `routes_config`, `fleet_config`, `crowding_reports`. SQLite locally, Postgres on Render (same SQL, keep it portable).
2. `scripts/seed_db.py`: creates tables, operator/admin users from env passwords, seeds route + fleet config from GTFS subset.
3. Auth (contract §4): `/auth/login`, JWT issue/verify, `require_role(...)` dependency.
4. Replay clock (`replay.py`): in-memory `{t, speed, playing, scenario}`; `t` advances by wall time × speed while playing. `GET/POST /clock`.
5. `GET /state`: buses at `t` from replay data + load estimate, `route_health` from B2, `feed` health.
6. `GET /routes`, `GET /buses`, `GET /eta` (ETA from travel-time model or recorded run times).
7. Pydantic schemas in `api/app/schemas.py` mirror contract §5 one-to-one.
8. Contract test `api/tests/test_contract.py`: for each endpoint, validate the real response against the fixture shape in `mock/fixtures/` (same keys, same types).
9. Deploy. Tell B the endpoints are live.

Done when: M1 joint test passes (contract §9): replay at ×30 shows moving buses on operator and rider maps via the Render URL.

---

## Phase B4 — Optimiser and explanations → unblocks **M2**

Files: `api/app/core/optimise.py`, `api/app/core/greedy.py`, `api/app/core/explain.py`, `api/app/templates/*.j2`, `api/app/routers/{cycle,decisions}.py`

1. CP-SAT model (solution2 §6.6): headway choice per route × 30-min band from {6, 8, 10, 12, 15, 20}; move variables donor → receiver incl. depot reserve; objective = wait + overcrowding + deadhead + change penalty; constraints = fleet per depot, min frequency, deadhead reachability, duty hours, ≤ 2 changes/route/hour. `num_workers=1`, `max_time_in_seconds=5`.
2. Greedy fallback when CP-SAT has no feasible answer in time. Set `solver` field accordingly.
3. Convert solution to `Recommendation` records (three actions only: `move_bus`, `add_trip`, `release_bus`) with `expected_effect` computed from the forecast.
4. Jinja2 template per action → `explanation`. All numbers come from the record.
5. `POST /cycle`: run forecast → detect → optimise if last cycle is ≥ 15 simulated minutes old; else return cached list with `ran=false`. Store recommendations in DB.
6. `GET /recommendations`, `POST /decisions` (409 if already decided; mark older pending ones `expired` when a new cycle runs), `GET /decisions`, `GET /decisions.csv`.
7. Approved recommendations change the replay fleet assignment for the rest of the window, so the operator map reflects the move.

Done when: event-surge scenario yields a `move_bus` card within 10 s on Render; approve/reject rows appear in Postgres and CSV.

---

## Phase B5 — Simulator → unblocks **M3**

Files: `api/app/sim/` (shared), `offline/sim/run_batch.py`, `api/app/routers/{whatif,results}.py`

1. SimPy model in `api/app/sim/` (one code base, used offline and online): buses, stops, boardings from demand, segment times from travel-time data, capacity.
2. Strategies: baseline, baseline + virtual-schedule holding, AduthaBus (holding + auto-approved reallocation).
3. Scenarios: normal weekday, heavy rain, event surge, breakdown.
4. Robustness: re-run each with demand error 0 / ±20% / ±40% / missed surge.
5. `run_batch.py` on laptop → `data/artefacts/results.json` in `ScenarioResult` shape (contract §5). `GET /results` serves it.
6. `POST /whatif`: 2-hour, one cluster, with vs without the recommendation. Target < 10 s on 0.1 CPU. If slower: coarser time step, fewer replications, cap passengers as groups.

Done when: `/whatif` finishes < 10 s on Render; `results.json` has all scenario × strategy × error rows.

---

## Phase B6 — Rider and admin endpoints → unblocks **M4**

Files: `api/app/routers/{rider,admin}.py`, `api/app/core/crowding.py`

1. `POST /auth/device`: issue `rider` JWT for a device UUID.
2. `POST /crowding`: store report; rate limit 1 per bus per 5 min per device (in-memory dict + DB check) → `429`.
3. Blend reports into load estimate (solution2 §6.3): weight by count and recency (e.g. exponential decay, 15-min half-life), cap influence at ±30% of the model estimate. Detection in the next `/state` or `/cycle` uses the blended value.
4. `GET /alerts`: generated from active flags + approved recommendations (`service_change`).
5. `/admin/routes` and `/admin/fleet` CRUD on `routes_config` / `fleet_config`. Fleet changes feed the optimiser's fleet constraint.
6. **Cut option:** if short on time, admin endpoints return seed JSON read-only and PUT/POST return `501`. Tell B early so F6 is skipped too.

Done when: M4 joint test passes: rider "Crowded" on Route 534 raises its load / flag on the operator map within one `/state` poll.

---

## Phase B7 — Hardening → **M5**

1. Memory check on Render under a full demo run (`/state` polling + `/cycle` + `/whatif`). If > 450 MB: switch to Polars/DuckDB, load only the current 2-hour window.
2. `scripts/export_log.py`: dump decisions + crowding reports to CSV. Calendar reminder before the 30-day Postgres expiry.
3. Optional live mode (`LIVE_MODE=true`): async GTFS-RT poll every 30 s while awake; `feed.mode="live"` only when fresh.
4. Optional free-LLM rewording adapter (off by default; template fallback on any error). Skip unless time remains.
5. Final `render.yaml`; pin all versions; tag `m5`.
6. Rehearse demo with B on Render URLs (solution2 §11). Wake API 2 min early.

---

## Testing

| Level | What |
|---|---|
| Unit | features, each detection flag, optimiser constraints (min frequency never violated), greedy fallback, templates, crowding blend cap |
| Contract | `api/tests/test_contract.py` — real responses vs `mock/fixtures/` shapes |
| Integration | scripted replay of event-surge day: `/clock` jump → `/cycle` → `/decisions` → `/whatif` |
| Deploy | after each deploy, `curl /health` and one `/state` call |

## Risks owned by A

| Risk | Mitigation |
|---|---|
| > 512 MB on Render | B0 measurement; Polars; 2-hour window; drop pandas |
| CP-SAT slow | 5 s limit, 1 worker, greedy fallback |
| `/whatif` > 10 s | coarser sim, fewer passengers as groups; B shows a progress state |
| GTFS-RT access fails | replay mode is default; recorded data in repo |
| Postgres expiry | export script, `schema.sql` + `seed_db.py` recreate in minutes |

## Handoff checklist (what Person B needs from A)

- [ ] **M0:** mock server + fixtures for every endpoint; Render API URL; `render.yaml` with slots for static sites
- [ ] **M0:** demo usernames (passwords shared privately, not in Git)
- [ ] **M1:** auth, clock, state, routes, buses, eta live on Render
- [ ] **M2:** cycle, recommendations, decisions, CSV live; a scenario + time that reliably produces a card (for B's testing)
- [ ] **M3:** whatif + results live; typical `/whatif` runtime
- [ ] **M4:** device auth, crowding, alerts, admin endpoints live (or the "admin cut" decision)
- [ ] Any contract change announced as a `contract/` PR before merge
