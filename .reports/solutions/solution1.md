# Solution 1: Network-Level Bus Reallocation Assistant

| Field | Value |
|---|---|
| Drafted | 2026-09-25 |
| Problem | AI-Based Dynamic Public Transport Scheduling (`problem-statement.md`) |
| Based on | `.reports/2026-09-25_ai-dynamic-bus-scheduling-existing-solutions.md` (cited below as "Report") |
| Working name | **AduthaBus** |
| Status | Draft for team review |

## 1. One-Line Pitch

AduthaBus is a decision-support system for bus control rooms. Every 15 minutes it forecasts demand and delays across a group of routes, flags overcrowded, underused, and delayed services, and recommends where to move buses. Each recommendation shows its reason and expected effect, and a dispatcher approves or rejects it with one click.

## 2. Why This Solution

The Report found that the problem's core loop (detect problems, then move capacity) is split across existing tools (Report, Analysis):

| Existing option | What it does | What it leaves out |
|---|---|---|
| Swiftly, Chalo, Google Maps | Show crowding, bunching, and delays | The decision: a person picks the action |
| Optibus, HASTUS, Trapeze | Build offline timetables; monitor live service | Moving buses between routes in real time based on demand |
| Academic RL (DRL-TO, multi-agent holding) | Makes control decisions automatically | Usually one route, in simulation, and hard to explain |
| DTC AI Bus Management tender | Plans for all of the above in Delhi | Still at tender stage; no working system yet |

AduthaBus fills this gap: it links detection to **network-level fleet reallocation**, and it is built for Indian data conditions (GPS feeds and ticket-machine data, but few passenger counters).

## 3. Scope

**In scope**

- A cluster of 4–6 routes that share a corridor and one or two depots (for example, one Delhi depot area).
- Recommendations for the next 30–120 minutes: add a trip, move a bus from route A to route B, release a bus from a quiet route, or hold or short-turn a bus to fix bunching.
- A simulator that measures results against today's fixed timetable.

**Out of scope for the hackathon**

- Full crew rostering and payroll (only a simple duty-hour check).
- Fully automatic control with no human approval.
- Rail and metro.

## 4. System Overview

```
 Data sources                 Core engine                          Dispatcher
 ------------                 -----------                          ----------
 GTFS static      ─┐
 GTFS-RT GPS      ─┼─► 1. Ingest & clean ─► 2. Load estimation
 Ticket data      ─┤        │                     │
 Calendar/weather ─┘        ▼                     ▼
                     3. Forecasting (demand, travel time)
                                  │
                                  ▼
                     4. Detection (crowding, underuse, delay, bunching)
                                  │
                                  ▼
                     5. Fleet reallocation optimiser  ◄── fleet, depot, duty limits
                     6. Real-time control rules (holding, short-turn)
                                  │
                                  ▼
                     7. Explanation layer ─────────────────► 8. Control-room console
                                  ▲                               (approve / reject)
                                  └──────── feedback log ◄────────────┘

                     9. Simulator: replays a day and scores each strategy
```

## 5. Components

### 5.1 Data ingestion and cleaning

| Source | Use | Availability |
|---|---|---|
| Delhi OTD static GTFS | Routes, stops, planned trips | Open (Report 5.2) |
| Delhi OTD GTFS-realtime | Bus positions every 10 s; source of speeds, headways, delays | Open with API key registration (Report 5.2) |
| Ticket-machine (ETM) boardings | Demand by stop and time | Not open; use synthetic data calibrated to public ridership figures, and state this clearly |
| Holiday calendar, weather, events | Forecast features | Public |

Cleaning rules (Report Recommendation 7):

- Match GPS points to route shapes, and drop points more than 50 m from the route.
- Mark a bus as "dark" if it sends no position for more than 2 minutes. Estimate its position from the schedule and its last known speed, and lower the confidence of any detection that depends on it.
- Show feed health (share of buses reporting) on the console.

### 5.2 Load estimation

Ticket machines record where passengers board but usually not where they get off. To estimate how full each bus is:

1. Assign each ticket's alighting stop from the fare stage when available.
2. Otherwise, spread alightings over downstream stops using stop "attraction" weights (from land use and historical patterns), then balance with iterative proportional fitting.
3. Output: estimated on-board load and load factor (load ÷ capacity) for each trip and route segment.

### 5.3 Forecasting

| Model | Target | Method | Horizon |
|---|---|---|---|
| Demand | Boardings per route, direction, stop group, and 15-minute band | LightGBM with quantile output (P50, P90) | 15–120 min, and day-ahead |
| Travel time | Running time per segment | LightGBM on GPS-derived segment speeds | 15–60 min |

- Features: time of day, day of week, holiday flag, weather, recent 30/60-minute boardings, recent segment speeds, upstream delays.
- Overcrowding is rare, so use sample weighting or focal loss for high-load cases, following the Vanderbilt/WeGo approach (Report 2.5).
- Stretch goal: a graph model over the stop network (Report 2.5).

### 5.4 Detection

Each 15-minute cycle, every route-direction is labelled:

| Flag | Rule (starting values, to be tuned) |
|---|---|
| Overcrowded | Forecast P90 load factor > 1.0 on any segment in the next 60 min, or observed passengers left behind |
| Underused | Forecast P50 load factor < 0.3 for 60 min or more |
| Delay emerging | Segment speed more than 2 standard deviations below its norm for the time band, or schedule delay > 5 min and growing |
| Bunching | Actual headway < 50% of planned headway between consecutive buses |

Each flag stores the evidence behind it (numbers, time window, confidence). The explanation layer uses this evidence.

### 5.5 Fleet reallocation optimiser (core feature)

A small mixed-integer program runs every 15 minutes for the next 2 hours, solved with Google OR-Tools (CP-SAT) or PuLP.

**Decisions**

- Frequency per route and time band, chosen from a fixed list (for example, every 6, 8, 10, 12, 15, or 20 minutes).
- Number of buses moved from each donor route or depot reserve to each receiving route.

**Objective** (minimise the weighted sum)

- Expected passenger waiting time ≈ demand × headway ÷ 2.
- Overcrowding penalty = expected passengers above capacity.
- Cost of empty travel (deadhead km) for moved buses.
- Change penalty, so the plan does not change too often.

**Constraints**

- Total buses in service ≤ available fleet per depot (minus buses under breakdown or charging).
- Every route keeps a minimum frequency (a service guarantee for riders).
- A moved bus must be able to reach its new route in time, based on deadhead travel time.
- Driver duty hours are not exceeded (simplified check).
- At most N changes per route per hour.
- Optional: an electric bus's battery charge must cover the new trip.

This follows the predict-then-optimise pattern that gave a 25.8% travel-time improvement on the Beijing network (Report 2.6), applied here to frequency and fleet instead of line shape.

### 5.6 Real-time control rules

- **Holding**: at control stops, hold buses against a "virtual schedule" (Xuan, Argote, and Daganzo). It is simple, needs only arrival times, and is the standard baseline (Report 2.1).
- **Short-turn suggestion**: when a bus is bunched behind another and the gap in the opposite direction is large, suggest turning it back early.
- RL-based holding is a stretch goal and must be shown to beat this baseline in the simulator (Report Recommendation 3).

### 5.7 Explanation layer

- Every recommendation is a structured record: action, trigger flags, evidence, expected change in waiting time and load, confidence, and cost (deadhead km).
- An LLM (for example, Claude) turns the record into one or two plain sentences. The optimiser makes the decision; the LLM only explains it and never changes the numbers (Report Recommendation 5).
- Example: *"Move 2 buses from Route 423 to Route 534 from 17:30 to 19:00. Route 534 is forecast to run at 125% capacity at Nehru Place (P90), and Route 423 is at 28%. Expected effect: average wait on 534 falls from 11 to 7 minutes; 423 keeps its minimum 15-minute frequency. Extra empty travel: 6 km."*

### 5.8 Control-room console

- Map of the route cluster with live buses, coloured by estimated load.
- Route health table: crowding, underuse, delay, and bunching flags.
- Recommendation queue: cards with **Approve**, **Reject** (with reason), or **Edit**.
- Feed health panel (share of buses reporting GPS).
- All decisions are logged. Rejection reasons become training data and help tune thresholds.

### 5.9 Simulator

A discrete-event simulator (SimPy) replays a service day on the chosen routes, using GTFS trips, the demand model, and travel-time distributions.

**Strategies compared**

1. Baseline: fixed timetable, no control.
2. Baseline + virtual-schedule holding.
3. AduthaBus: holding + 15-minute reallocation (recommendations auto-approved in simulation).

**Scenarios**

- Normal weekday.
- Heavy rain (slower segments, higher demand).
- Event surge at one stop (for example, a stadium or a market).
- Bus breakdown on a busy route.

**Metrics** (the same types used in published work, Report 2.2 and 2.4)

| Metric | Direction |
|---|---|
| Average and 95th-percentile waiting time | Lower is better |
| Passengers left behind | Lower is better |
| Minutes of service above 100% load factor | Lower is better |
| Bunching events | Lower is better |
| Average load factor (bus utilisation) | Higher is better, up to a comfort limit |
| Deadhead km | Lower is better |
| Number of plan changes per hour | Kept within the limit |

## 6. Technology Stack

| Layer | Choice | Reason |
|---|---|---|
| Data processing | Python, pandas, DuckDB | Fast to build; handles GTFS easily |
| GTFS tools | `gtfs-kit` or `partridge`, `gtfs-realtime-bindings` | Standard parsers |
| Forecasting | LightGBM | Strong on tabular data; quick to train; supports quantiles |
| Optimisation | OR-Tools CP-SAT | Free; handles integer decisions well |
| Simulation | SimPy | Simple discrete-event modelling in Python |
| API | FastAPI | Lightweight; async support for live feeds |
| Console | React + MapLibre GL | Free map rendering; good live updates |
| Explanations | Claude API | Plain-language text from structured records |
| Storage | PostgreSQL (or SQLite for the demo) | Stores the recommendation log and history |

## 7. Differentiation

| Point | AduthaBus | Typical existing tool |
|---|---|---|
| Scope | Several routes, one shared fleet | One route, or display only |
| Output | Specific action with expected effect | Alert or dashboard |
| Explainability | Evidence and plain-language reason on each card | Black-box score or none |
| Human control | Approve, reject, or edit; feedback is logged | Fully manual, or fully automatic in research |
| Indian data | Works with GPS + ticket data; estimates loads; handles GPS gaps | Assumes passenger counters and clean feeds |
| Proof | Simulator results against today's timetable | Vendor claims |

## 8. Build Plan

Phases in order of priority. If time runs short, stop after Phase 3; the result is still a complete demo.

| Phase | Deliverable | Share of effort |
|---|---|---|
| 1. Data | GTFS for chosen routes loaded; live GPS feed parsed; synthetic ticket data generated | 15% |
| 2. Forecast + detection | Demand and travel-time models; four flags working on replayed data | 20% |
| 3. Optimiser + simulator | Reallocation model; simulator with baseline vs AduthaBus results | 30% |
| 4. Console | Map, route health table, recommendation cards with approve/reject | 20% |
| 5. Explanations + polish | LLM explanations; scenario demos; result charts | 15% |

**Suggested team split (4 people):** data and forecasting; optimiser and simulator; backend API; frontend console. Everyone helps with the demo in the last phase.

## 9. Demo Script (3 minutes)

1. Show the live map of the route cluster on a normal afternoon.
2. Start the "event surge" scenario. Route 534 turns red: forecast load 125%.
3. A recommendation card appears: move 2 buses from underused Route 423. Read the explanation.
4. Approve it. The simulator shows waiting time and crowding falling on 534, while 423 keeps its minimum service.
5. End with the results table: baseline vs holding only vs AduthaBus, across all four scenarios.

## 10. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Ticket data is not openly available | Demand model trained on synthetic data | Calibrate to published ridership; say so clearly; design the input so real ETM data can be plugged in |
| GTFS-RT access or quality problems | No live demo | Record a few hours of the feed in advance and replay it |
| Simulated gains do not carry over to real service | Judges question the results | Report the baseline and the assumptions; show sensitivity to demand error |
| Dispatchers do not trust the recommendations | Low adoption | Explanations, confidence levels, human approval, and a limit on changes per hour |
| Frequent changes confuse riders and drivers | Poor service in practice | Change penalty and per-hour limit in the optimiser; publish updates to the rider app feed |
| Optimiser too slow for a large network | Recommendations arrive late | Solve per depot cluster; the 15-minute cycle leaves time |
| LLM writes wrong numbers | Misleading explanations | LLM only rewords the structured record; numbers are inserted from the record, and the output is checked against it |

## 11. Open Questions for the Team

1. Which Delhi route cluster and depot should we use? It should have both a busy route and a quiet route that share a depot.
2. Is the hackathon judged more on a live demo or on measured results? This changes the effort split between the console and the simulator.
3. Can we get any real ETM or passenger-count sample from DTC, DIMTS, or BMTC? Even a small sample would make the load estimation much more credible.
4. Do we include electric-bus charging limits in the MVP, given that DTC runs over 4,500 e-buses (Report 5.2)?
5. How long is the hackathon? The build plan above uses effort shares because the duration is not known.
