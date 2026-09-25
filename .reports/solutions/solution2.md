# Solution 2: TransitPulse Lite — Zero-Budget Bus Reallocation Assistant

| Field | Value |
|---|---|
| Drafted | 2026-09-25 |
| Problem | AI-Based Dynamic Public Transport Scheduling (`.data/problem-statement.md`) |
| Constraints | `.data/constraints.md` (zero budget; all cloud parts on Render free tier) |
| Based on | `solution1.md`, reworked after `solution1-review.md`; landscape report `.reports/2026-09-25_ai-dynamic-bus-scheduling-existing-solutions.md` ("Report") |
| Working name | **TransitPulse Lite** |
| Status | Draft for team review |

## 1. One-Line Pitch

TransitPulse Lite is a free, three-portal decision-support system for bus networks. One API and one database serve an **operator console** (dispatchers approve or reject reallocation recommendations), a **fleet admin portal** (bus providers configure routes, depots, and fleet size), and a **rider app** (passengers see live buses and report crowding, feeding real demand data back into the forecast). Each recommendation shows its reason and expected effect. The whole system costs nothing to run and is hosted entirely on Render's free tier.

## 2. What Changed from Solution 1

The core idea is the same: network-level fleet reallocation with human approval (see Solution 1, Section 2, for why this fills a gap). The delivery is redesigned to meet the project constraints.

| Area | Solution 1 | Solution 2 | Reason |
|---|---|---|---|
| Explanations | Claude API | Text templates (Jinja2); optional free LLM tier, off by default | Claude API is paid |
| Cycle trigger | Timer every 15 minutes | Request-driven, on a replay clock | Free web services sleep after 15 minutes idle; no free workers or cron jobs |
| Model training | Not specified (implied server) | Offline on laptops; artefacts committed to the repository | 512 MB RAM and 0.1 CPU on the free instance |
| Simulator | Server-side | Full scenario batch offline; small what-if runs online | Same compute limit |
| Storage | PostgreSQL or SQLite | Static data in the repository; decision log in free Render Postgres, with CSV export | Ephemeral filesystem; free Postgres expires after 30 days |
| Map tiles | Not specified | OpenFreeMap (free, no key) | Most tile APIs need billing |
| Scope | 5 actions, edit, learning from rejections, EV option | 3 actions; other items moved to future work | Hackathon time; demo reliability |
| Results | Against synthetic demand | Also against demand with added forecast error | Answers the "synthetic data is circular" concern |
| Frontend | One control-room console | Three portals: operator, fleet admin, rider — one API, one DB | Serves both sides named in the problem statement (providers and passenger demand); rider reports add a real demand signal |
| Rider app platform | Not specified | Flutter, built for **Web** target, deployed as a static site | Native app store listing breaks zero-budget ($25–$99 fees); Flutter Web has no store fee and deploys like any static site |

## 3. Constraint Compliance

| Constraint | How the design meets it |
|---|---|
| Zero budget | Only open-source libraries, open data, and free tiers that need no payment method. No paid API is required at any point. |
| All cloud parts on Render | Frontend on a Render static site. API on a Render free web service. Decision log on a Render free Postgres database. No other cloud host. |
| Free web service sleeps when idle | The cycle is request-driven, and the replay clock does not depend on wall time. A wake-up screen covers the roughly one-minute cold start. |
| Limited compute (512 MB, 0.1 CPU) | Training and heavy simulation run offline. The server only loads small artefacts, runs inference, and solves one small optimisation per cycle with a time limit. |
| Limited, non-persistent storage | Read-only data ships in the repository. Only the decision log uses the database. The log can be exported as CSV at any time. |
| 750 free instance hours per month | One web service uses at most 744 hours in a 31-day month. Spun-down time does not count. |

Development tools are also free: GitHub for code (Render deploys from it), and team laptops for offline work. A laptop is not a cloud part, so it does not conflict with the Render rule.

## 4. Scope

**In scope**

- A cluster of 4–6 Delhi routes that share a corridor and one or two depots.
- Recommendations for the next 30–120 minutes of three types:
  1. Move a bus from route A to route B.
  2. Add a trip from the depot reserve.
  3. Release a bus from a quiet route to the depot.
- Four detection flags: overcrowded, underused, delay emerging, bunching.
- A simulator that compares TransitPulse Lite against today's fixed timetable and against virtual-schedule holding.
- Three portals sharing one API: operator console (dispatch), fleet admin portal (thin config only), rider app (live view + crowding reports).

**Future work (not in the hackathon build)**

- Short-turn suggestions and live holding instructions (holding stays as a simulator baseline).
- Editing a recommendation before approval.
- Tuning thresholds from rejection reasons (reasons are logged, but no learning is claimed).
- Electric-bus charge limits.
- Crew rostering.

## 5. System Overview

```
 OFFLINE LANE (team laptops, free)                 ONLINE LANE (Render free tier)
 ---------------------------------                 ------------------------------
 Delhi OTD GTFS static ─┐                          3 Render static sites
 Recorded GTFS-RT feed ─┼─► clean + map-match       ├─ Operator console  (React + MapLibre)
 Synthetic ETM data    ─┤        │                  ├─ Fleet admin portal (React, forms)
 Open-Meteo weather    ─┘        ▼                  └─ Rider app (Flutter, Web target)
                         train LightGBM models              │
                         run full SimPy batch                ▼ HTTPS (JSON, JWT auth)
                                 │                 Render free web service (FastAPI)
                                 ▼                   1. Replay clock / optional live poll
                         artefacts in Git repo ───►  2. Load estimation (+ rider crowding reports)
                         (model .txt, Parquet,       3. Forecast (inference only)
                          scenario JSON)             4. Detection
                                                     5. Reallocation optimiser (CP-SAT, 5 s)
                                                     6. Template explanations
                                                     7. Small what-if simulation
                                                     8. Route/fleet config CRUD (admin only)
                                                          │
                                                          ▼
                                                   Render free Postgres
                                                   decision log + route/fleet config
                                                   + rider crowding reports (+ CSV export)
```

Three frontends, one API, one database. Role claim in the JWT (`operator`, `admin`, `rider`) gates which endpoints each portal can call.

## 6. Components

### 6.1 Data (offline lane)

| Source | Use | Cost and access |
|---|---|---|
| Delhi OTD static GTFS | Routes, stops, shapes, planned trips | Free, open |
| Delhi OTD GTFS-realtime | Bus positions; source of speeds, headways, delays | Free with API key registration |
| Ticket-machine (ETM) boardings | Demand by stop and time | Not open. Generated synthetically (see 6.3). |
| Open-Meteo | Hourly weather features | Free, no key |
| Public holiday list | Calendar feature | Free, public |

Steps:

1. Filter static GTFS to the chosen route cluster. Save as Parquet (a few MB).
2. Record the GTFS-RT feed from a laptop for at least 3 weekdays and 1 weekend day. Save one row per position.
3. Clean positions: match to route shapes, drop points more than 50 m from the route, and mark a bus as "dark" after 2 minutes without a report.
4. Derive segment running times, headways, and delays. Save as Parquet.

### 6.2 Load estimation

Same method as Solution 1, Section 5.2: assign alighting stops from fare stages where possible, otherwise spread alightings with stop attraction weights and balance with iterative proportional fitting. Output: estimated load and load factor per trip and segment. The method runs offline for training data and online for the current replay window (small enough to fit in memory).

### 6.3 Synthetic demand generator

The demand model needs boardings, and no open ETM data exists. The generator:

- Uses a documented formula: base rate per stop (from stop type and land use) × time-of-day profile × day-type factor × weather factor × event factor.
- Is calibrated so daily route totals match published DTC ridership figures.
- Is published in the repository with its parameters, so judges can inspect it.
- Accepts real ETM files in the same schema, so real data can replace it without code changes.
- **Rider crowding reports** (Section 6.10) are blended in as a real, non-synthetic signal: each report nudges the load estimate for that route-segment-time slot, weighted by report count and recency. This is the direct fix for critique 6 (synthetic demand is otherwise circular).

### 6.4 Forecasting

| Model | Target | Method | Horizon |
|---|---|---|---|
| Demand | Boardings per route, direction, stop group, and 15-minute band | LightGBM, quantile objective (P50, P90) | 15–120 min |
| Travel time | Running time per segment | LightGBM | 15–60 min |

- Training runs offline. Models are saved in LightGBM text format (typically under 5 MB each) and committed to the repository.
- The server loads the models once at start-up and runs inference only.
- Features: time of day, day of week, holiday flag, weather, recent 30/60-minute boardings, recent segment speeds, upstream delays.
- Use sample weights to give more importance to high-load cases, which are rare.

### 6.5 Detection

Each cycle labels every route-direction:

| Flag | Rule (starting values, to be tuned) |
|---|---|
| Overcrowded | Forecast P90 load factor > 1.0 on any segment in the next 60 minutes |
| Underused | Forecast P50 load factor < 0.3 for 60 minutes or more |
| Delay emerging | Segment speed more than 2 standard deviations below its norm for the time band, or schedule delay > 5 minutes and growing |
| Bunching | Actual headway < 50% of planned headway between consecutive buses |

Each flag stores its evidence: numbers, time window, and confidence. Confidence drops when a flag depends on a dark bus.

### 6.6 Fleet reallocation optimiser (core feature)

A small integer program solved with OR-Tools CP-SAT (free, open source).

**Decisions**

- Headway per route and 30-minute band, chosen from a fixed list: 6, 8, 10, 12, 15, or 20 minutes.
- Number of buses moved from each donor route or the depot reserve to each receiving route.

**Objective** (minimise the weighted sum)

- Expected passenger waiting time ≈ demand × headway ÷ 2.
- Overcrowding penalty = expected passengers above capacity.
- Deadhead kilometres for moved buses.
- Change penalty, so the plan stays stable.

**Constraints**

- Buses in service ≤ available fleet per depot, minus breakdowns.
- Every route keeps a minimum frequency (service guarantee).
- A moved bus must reach its new route in time, based on deadhead travel time.
- Simplified driver duty-hour check.
- At most 2 changes per route per hour.

**Fitting the free instance**

- Problem size: 6 routes × 4 bands × 6 headway options, plus move variables. This is a few hundred variables.
- Solver settings: `num_workers=1`, `max_time_in_seconds=5`.
- If the solver has no feasible answer in time, a greedy fallback moves one bus at a time from the most underused route to the most overcrowded route while all constraints hold.

### 6.7 Explanations (templates, no paid LLM)

Every recommendation is a structured record: action, trigger flags, evidence, expected change in waiting time and load, confidence, and deadhead cost. A Jinja2 template per action type turns it into plain text. All numbers come directly from the record, so the text cannot contain wrong numbers.

Example output of the "move bus" template:

> *Move 2 buses from Route 423 to Route 534, 17:30–19:00. Route 534 is forecast at 125% of capacity near Nehru Place (P90); Route 423 is at 28%. Expected effect: average wait on 534 falls from 11 to 7 minutes; 423 keeps its 15-minute minimum frequency. Extra empty travel: 6 km. Confidence: high.*

Optional: an adapter for a free LLM tier that needs no payment method (for example, Google AI Studio's free Gemini tier) can reword the template text. It is off by default, it receives only the finished template text, and the app falls back to the template on any error, timeout, or rate limit. The demo does not depend on it.

### 6.8 API service (Render free web service)

FastAPI, one process. Main endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /health` | Wake-up check; returns load status of models and data |
| `GET /state?t=` | Bus positions, route health flags, and feed health at replay time `t` |
| `POST /cycle?t=` | Runs forecast, detection, and optimisation for time `t`, if the last cycle is more than 15 simulated minutes old; returns recommendations |
| `POST /decisions` | Stores approve or reject, with a reason |
| `GET /decisions.csv` | Exports the decision log |
| `POST /whatif` | Runs a 2-hour simulation of one route cluster with and without a recommendation |
| `GET /results` | Returns precomputed scenario results from the offline batch |
| `GET /routes`, `GET /buses` | Public route and live-bus data (rider app) |
| `POST /crowding` | Rider submits a crowding report for the bus they're on (auth: rider) |
| `GET/POST/PUT /admin/routes`, `/admin/fleet` | Route and fleet config CRUD (auth: admin) |
| `POST /auth/login` | Issues a JWT with a role claim (`operator`, `admin`, `rider`) |

Role claim in the JWT gates each group. No paid identity vendor — self-rolled JWT with FastAPI + passlib.

**Replay clock:** The default mode replays a recorded service day. The console controls the clock (play, pause, speed ×10 or ×30, jump to scenario start). The server is stateless between requests except for a small in-memory cache, so a restart or spin-down loses nothing important.

**Optional live mode:** While the service is awake, an async task polls GTFS-RT every 30 seconds for the route cluster only. The console shows "live" only when data is fresh. The demo does not depend on live mode.

**Memory budget (target, to be checked in the validation step):**

| Item | Target |
|---|---|
| Python, FastAPI, pandas, PyArrow | ~150 MB |
| LightGBM and two models | ~50 MB |
| OR-Tools | ~100 MB |
| Replay data for one day, one cluster | ~50 MB |
| Headroom | ~160 MB |
| **Total** | **≤ 512 MB** |

If the total is too high, replace pandas with Polars or DuckDB for the replay data, and load only the current 2-hour window.

### 6.9 Storage

| Data | Where | Why |
|---|---|---|
| GTFS subset, cleaned feed, model files, scenario results | Git repository, loaded at start-up | Read-only; survives restarts because it ships with each deploy |
| Decision log | Render free Postgres (1 GB) | Only data written at run time |
| Local development | SQLite | No database setup needed |

Free Postgres expires 30 days after creation. The team runs `scripts/export_log.py` before expiry and can recreate the database from a schema file in minutes. The console also has an "Export CSV" button.

### 6.10 Frontends — three portals, three Render static sites

One API, one database, three deployable frontends. Each is a separate Render static site (multiple static sites are free; only the one API and one database count against paid-tier-shaped limits).

#### 6.10.1 Operator console (dispatchers)

React + Vite + MapLibre GL, built to static files.

- **Wake-up screen:** On load, calls `/health` every 3 seconds and shows "Starting server (about 1 minute)…" until the API answers.
- **Map:** MapLibre GL with OpenFreeMap vector tiles. Route shapes and buses are GeoJSON layers; buses coloured by estimated load. If tiles fail, shows routes on a plain background.
- **Route health table:** The four flags per route-direction, with evidence on hover.
- **Recommendation queue:** Cards with the explanation, **Approve**, and **Reject** (with a reason).
- **What-if panel:** Before approving, the dispatcher can run a short simulation and see expected waiting time and load with and without the change.
- **Results tab:** Charts of the offline scenario batch.
- **Feed health:** Share of buses reporting.

#### 6.10.2 Fleet admin portal (bus providers)

React + Vite, plain forms. Kept deliberately thin: fleet and route CRUD is already owned by commercial tools (Optibus, HASTUS, Trapeze — Report table), so it adds no differentiation and should not absorb hackathon time.

- Add/edit a route (stops, shape reference, minimum frequency).
- Set fleet size and reserve count per depot.
- View decision log (read-only) and export CSV.
- **Cut first if time runs short:** mock this with a seed JSON file loaded at start-up instead of building CRUD screens.

#### 6.10.3 Rider app (passengers)

Flutter, built for the **Web** target (`flutter build web`) — not a native store app. Compiles to static files, deployed as a third Render static site. Installable via "Add to Home Screen" on phones; no Play Store ($25) or App Store ($99/yr) fee, which would otherwise break the zero-budget rule. A native APK can be built and sideloaded for a live demo if wanted, free but not store-distributed.

- Live map of the route cluster, current bus positions, ETA at the rider's stop.
- **One-tap crowding report:** "Crowded" / "OK" / "Empty" on the bus the rider is on. This is the real (non-synthetic) demand signal described in Section 6.3.
- Service alerts (delay, bunching) for the routes the rider follows.
- No login required for viewing; a lightweight anonymous device ID rate-limits crowding reports to stop spam, no account system needed for the demo.

### 6.11 Simulator

A discrete-event simulator in SimPy, the same code offline and online.

- **Offline (laptops):** Full service days for all strategies and scenarios. Results saved as JSON and shown in the Results tab.
- **Online (what-if):** One route cluster, 2 hours, one strategy pair. Target run time under 10 seconds on 0.1 CPU.

**Strategies**

1. Baseline: fixed timetable, no control.
2. Baseline + virtual-schedule holding.
3. TransitPulse Lite: holding + reallocation (recommendations auto-approved in simulation).

**Scenarios**

- Normal weekday.
- Heavy rain (slower segments, higher demand).
- Event surge at one stop.
- Bus breakdown on a busy route.

**Robustness test (answers the synthetic-data concern):** Run every scenario again with forecast error added to demand (±20% and ±40%), and one case where the forecast misses a surge completely. Report how much of the gain remains.

**Metrics**

| Metric | Direction |
|---|---|
| Average and 95th-percentile waiting time | Lower is better |
| Estimated passengers left behind | Lower is better |
| Minutes of service above 100% load factor | Lower is better |
| Bunching events | Lower is better |
| Average load factor | Higher is better, up to a comfort limit |
| Deadhead km | Lower is better |
| Plan changes per hour | Within the limit |

## 7. Technology Stack

Every item is free and open source, or a free tier that needs no payment method.

| Layer | Choice | Licence or tier |
|---|---|---|
| Data processing | Python, pandas or Polars, DuckDB, PyArrow | Open source |
| GTFS | `gtfs-kit`, `gtfs-realtime-bindings` | Open source |
| Forecasting | LightGBM | Open source (MIT) |
| Optimisation | OR-Tools CP-SAT | Open source (Apache 2.0) |
| Simulation | SimPy | Open source (MIT) |
| API | FastAPI, Uvicorn | Open source |
| Explanations | Jinja2 templates | Open source |
| Operator + admin frontends | React, Vite, MapLibre GL | Open source |
| Rider frontend | Flutter (Web target) | Open source |
| Auth | Self-rolled JWT (FastAPI + passlib) | Open source; no paid identity vendor |
| Map tiles | OpenFreeMap | Free, no key |
| Weather | Open-Meteo | Free, no key |
| Database | Render Postgres (free) | Render free tier |
| Hosting | 3 Render static sites + 1 Render web service (free) | Render free tier |
| Code and deploy trigger | GitHub | Free |

## 8. Deployment on Render

Define both services and the database in one `render.yaml` Blueprint in the repository:

- `transitpulse-operator`: static site. Build command `npm ci && npm run build`. Publish directory `operator/dist`. Environment variable `VITE_API_URL`.
- `transitpulse-admin`: static site. Build command `npm ci && npm run build`. Publish directory `admin/dist`. Environment variable `VITE_API_URL`.
- `transitpulse-rider`: static site. Build command `flutter build web`. Publish directory `rider/build/web`. API URL baked in at build time or read from `window.location`.
- `transitpulse-api`: web service, Python, free plan. Build command `pip install -r api/requirements.txt`. Start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Health check path `/health`.
- `transitpulse-db`: Postgres, free plan. Its connection string goes to the API as `DATABASE_URL`.

Rules for the team:

- Three static sites, but only **one** web service and **one** database — that is what counts against the 750 free instance-hours and the one-free-database-per-workspace limits. Static sites cost nothing extra.
- Keep one web service only, so the 750 free instance hours are enough.
- Keep committed artefacts small (target under 100 MB total) to keep builds and deploys fast.
- Pin library versions in `requirements.txt` so builds are repeatable.
- Before a demo, open the console 2 minutes early to wake the API.

## 9. Differentiation

| Point | TransitPulse Lite | Typical existing tool |
|---|---|---|
| Scope | Several routes, one shared fleet | One route, or display only |
| Output | Specific action with expected effect | Alert or dashboard |
| Explainability | Evidence and a plain-language reason on each card | Black-box score or none |
| Human control | Approve or reject; decisions logged | Fully manual, or fully automatic in research |
| Indian data | Works with GPS and ticket data; handles GPS gaps | Assumes passenger counters and clean feeds |
| Proof | Simulator results, including under forecast error | Vendor claims |
| Cost | Zero: open source and free hosting | Commercial licences |
| Demand data | Rider crowding reports supplement synthetic and ticket data | Rely only on counters or manual surveys |

## 10. Build Plan

If time runs short, stop after Phase 3; the result is still a complete, deployed demo.

| Phase | Deliverable | Share of effort |
|---|---|---|
| 0. Validation | Toy deploy on Render free: imports, one model, toy CP-SAT solve; record memory and cold start | 5% |
| 1. Data | GTFS subset; recorded GTFS-RT; cleaning; synthetic ETM generator | 15% |
| 2. Forecast + detection | Two models trained offline; four flags working on replay data | 15% |
| 3. Optimiser + simulator + deploy | CP-SAT model with greedy fallback; offline scenario batch; API and operator console live on Render | 25% |
| 4. Operator console | Map, route table, recommendation cards, what-if panel, results tab | 15% |
| 5. Rider app | Flutter Web build: live map, ETA, one-tap crowding report, deployed as static site | 15% |
| 6. Fleet admin portal | Route/fleet CRUD forms (cut first if time is short; replace with a seed JSON file) | 5% |
| 7. Polish | Templates, robustness results, demo script rehearsal | 5% |

**Suggested team split (4 people):** data and forecasting; optimiser and simulator; API, auth, and deployment; frontends (operator console first, then rider app, admin portal last if time allows).

**If time is very short:** stop after Phase 4. Rider app and admin portal are additive, not required for the core AI loop the problem statement judges.

## 11. Demo Script (3 minutes)

1. Open the operator console (woken 2 minutes earlier). Show the map of the route cluster on a normal afternoon in replay mode.
2. Switch to the rider app on a phone or a second window: tap "Crowded" on Route 534. Show the report land in the load estimate.
3. Jump to the "event surge" scenario on the console. Route 534 turns red: forecast load 125%, boosted by the rider report just sent.
4. A recommendation card appears: move 2 buses from underused Route 423. Read the explanation.
5. Run the what-if panel: waiting time and crowding fall on 534, and 423 keeps its minimum service. Approve.
6. Open the Results tab: baseline vs holding vs TransitPulse Lite across four scenarios, and how much gain remains under ±40% forecast error.
7. Close with the cost line: three portals, one API, one database — the whole system runs on free tools and free hosting.

## 12. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| API exceeds 512 MB on the free instance | Crashes | Phase 0 measurement; Polars or DuckDB instead of pandas; load only the current 2-hour window |
| Cold start during judging | One-minute blank screen | Wake-up screen; open the app early; replay mode needs no warm cache |
| Free Postgres expires after 30 days | Decision log lost | CSV export; export script; schema file to recreate the database |
| GTFS-RT access fails or changes | No live data | Replay mode is the default; recorded feed is in the repository |
| Synthetic demand questioned | Results doubted | Published generator; robustness test under forecast error; plug-in slot for real ETM data |
| CP-SAT slow on 0.1 CPU | Late recommendations | 5-second limit; single worker; greedy fallback |
| OpenFreeMap tiles unavailable | Map has no basemap | Plain-background fallback with route GeoJSON |
| Frequent changes confuse riders and drivers | Poor service in practice | Change penalty; at most 2 changes per route per hour |
| Three frontends is too much build for a 4-person team | Rider app or admin portal unfinished at deadline | Fixed priority order (Section 10): operator console first, rider app second, admin portal cut first and replaced by a seed JSON file |
| Rider crowding reports get spammed or gamed | Bad data poisons the load estimate | Rate-limit by anonymous device ID; weight reports by recency and count; cap their influence relative to the model forecast |
| Flutter Web is less mature than Flutter native (larger bundle, slower first load) | Rider app feels sluggish on the demo phone | Keep the rider app to a few screens; test load time on the actual demo device beforehand; fall back to a plain React PWA if Flutter Web bundle size is a problem |

## 13. Open Questions for the Team

1. Which Delhi route cluster and depot should we use? It needs a busy route and a quiet route that share a depot.
2. How long is the hackathon? If it runs past 30 days, plan when to recreate the free Postgres database.
3. Is judging based more on the live demo or on measured results? This changes the effort split between the console and the simulator.
4. Can we get any real ETM or passenger-count sample from DTC, DIMTS, or BMTC? Even a small sample would test the synthetic generator.
5. Do we want the optional free LLM adapter at all, or keep templates only?
6. Is the fleet admin portal worth building for the demo, or does a seed JSON file plus a mention in the pitch cover it?
7. Flutter Web vs a plain React PWA for the rider app — does the team have more Flutter or React experience going into the hackathon?
