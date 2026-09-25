# Solution Review: Solution 1 (AduthaBus) against project constraints

| Field | Value |
|---|---|
| Reviewed | 2026-09-25 |
| Reviewed document | `.reports/solutions/solution1.md` |
| Checked against | `.data/problem-statement.md`, `.data/constraints.md` |
| Output | `.reports/solutions/solution2.md` (reworked solution) |

## 1. Understanding

**Problem:** Transit agencies run fixed bus timetables that do not react to real demand, traffic, delays, or fleet availability. This causes long waits, overcrowded buses on some routes, empty buses on others, and poor fleet use. The system must analyse historical and real-time data, detect overcrowding, underuse, and emerging delays, and recommend changes to frequency and deployment. The project has zero budget, and every cloud-hosted part must run on Render's free tier.

**Proposed solution:** AduthaBus is a control-room decision-support tool. Every 15 minutes it forecasts demand and travel time (LightGBM), flags four conditions (crowding, underuse, delay, bunching), and runs a fleet reallocation optimiser (OR-Tools CP-SAT). It adds holding and short-turn rules, an LLM explanation layer (Claude API), a React/MapLibre console with approve/reject, a PostgreSQL decision log, and a SimPy simulator that compares strategies.

**Assumptions made in this review:**

- Render free web service limits: 512 MB RAM, 0.1 CPU, spins down after 15 minutes without inbound traffic, takes about one minute to spin up, 750 free instance hours per month, and has an ephemeral filesystem (Render docs, "Deploy for Free").
- Background workers, cron jobs, and persistent disks are not available on the free tier.
- Render free Postgres: 1 GB, one per workspace, no backups, and it expires 30 days after creation.
- The hackathon lasts less than 30 days, or the team can recreate the database once.

## 2. Problem–Solution Fit: Strong on the problem, Weak on the constraints

The design covers every part of the problem statement: demand, traffic, delays, congestion, vehicle availability, detection, and recommendations for frequency and deployment. The simulator also gives a way to measure the stated goals (waiting time, crowding, delays, utilisation).

The constraints were not considered. The document names one paid service (Claude API) and assumes an always-on, scheduled backend with persistent storage. Render's free tier provides none of these. As written, the system cannot be deployed within the project's limits.

## 3. Strengths

### Unique features

- **Network-level fleet reallocation**: Moving buses between routes that share a depot is the gap the landscape report found. Tools such as Swiftly and Chalo show problems but do not decide. Optibus and HASTUS plan offline. This is a real differentiator.
- **Built for Indian data conditions**: Load estimation from ticket-machine boardings and handling of dark GPS buses fit Delhi's data better than tools that assume passenger counters.
- **Evidence on each recommendation**: Every card carries its trigger flags, numbers, and expected effect. This builds dispatcher trust and makes the demo easy to follow.

### Helping features

- **Human approval with a change limit**: The optimiser's change penalty and per-hour limit reduce rider confusion and keep the system realistic.
- **Simulator with a fair baseline**: Comparing against fixed timetable and virtual-schedule holding answers the judges' question "is it better than today?"
- **Mostly open-source stack**: Python, LightGBM, OR-Tools, SimPy, FastAPI, React, and MapLibre are all free. Only a few parts break the constraints, so the rework is small.
- **Phased build plan**: Stopping after Phase 3 still gives a complete demo.

## 4. Critiques and Suggested Fixes

**Critique 1: Paid LLM for explanations** — Severity: 🔴 Critical
**Issue:** The Claude API needs a payment method. This breaks the zero-budget rule. The design already says the LLM must not change numbers, so the LLM adds risk and cost but little value.
**Suggested fix:** Generate explanations from fixed text templates (Jinja2), filled from the structured recommendation record. Write one template per action type (add trip, move bus, release bus, hold, short-turn). If the team wants more natural text later, add an optional adapter for a free LLM tier that needs no payment method (for example, Google AI Studio's free Gemini tier). Keep it off by default, and fall back to templates on any error or rate limit.
**Trade-off:** Template text sounds less natural. In return, it is free, instant, always correct, and works offline.

**Critique 2: 15-minute cycle assumes an always-on backend** — Severity: 🔴 Critical
**Issue:** The free web service sleeps after 15 minutes without inbound traffic. Background workers and cron jobs are not free. A 15-minute scheduled cycle and a 10-second GPS poller will therefore stop whenever no one has the console open. Judges who open the link cold will wait about a minute and see stale data.
**Suggested fix:** Make the cycle request-driven, not timer-driven. Run the pipeline when the console asks for it and the last cycle is more than 15 minutes old in simulation time. Use a replay clock as the default mode: a recorded service day plays back at a set speed, so the cycle does not depend on wall-clock time. Add a "waking the server" screen on the static frontend that pings `/health` and shows progress. Open the app 2 minutes before judging.
**Trade-off:** Live mode only works while someone uses the app. Replay mode is less impressive than true live data, but it is reproducible and cannot fail on stage.

**Critique 3: Model training and full simulations do not fit 512 MB and 0.1 CPU** — Severity: 🔴 Critical
**Issue:** Training LightGBM, running multi-scenario SimPy experiments, and holding pandas, LightGBM, and OR-Tools in memory together can exceed 512 MB or take minutes on 0.1 CPU. The service may crash or time out.
**Suggested fix:** Split work into two lanes. The offline lane runs on team laptops: data cleaning, model training, calibration, and the full scenario batch. It commits small artefacts to the repository: model files (LightGBM text format), Parquet data for the route cluster, and scenario results as JSON. The online lane on Render only loads these artefacts, runs inference, and solves one small optimisation per cycle. Give CP-SAT `num_workers=1` and a 5-second time limit, with a greedy fallback. Measure peak memory locally with the same limit (`docker run --memory=512m --cpus=0.1`).
**Trade-off:** Models do not retrain online. Retraining becomes a manual step before each deploy.

**Critique 4: Storage is not persistent** — Severity: 🟠 Major
**Issue:** The document suggests PostgreSQL, or SQLite for the demo. On a free web service, a SQLite file disappears on every restart, spin-down, and deploy. Render free Postgres works but expires after 30 days and has no backups. The decision log and feedback loop would be lost.
**Suggested fix:** Keep all static data (GTFS subset, model files, recorded feed, scenario results) in the repository, since it is read-only. Store only the decision log in one Render free Postgres database. Add an "Export log as CSV" button and a small script that dumps the log before the 30-day expiry. Keep SQLite as a local development fallback only.
**Trade-off:** The team must recreate the database if the project runs longer than 30 days.

**Critique 5: No free map tile source named** — Severity: 🟠 Major
**Issue:** MapLibre GL needs a tile provider. Many providers need an API key with billing, and the public OpenStreetMap tile servers do not allow heavy app use. Without a free source, the map will not load.
**Suggested fix:** Use OpenFreeMap vector tiles (free, no key, no sign-up) as the basemap. Keep route shapes and bus markers as GeoJSON layers served by the API.
**Trade-off:** The team has no service-level agreement for the tiles. Keep a plain GeoJSON-only fallback view if tiles fail.

**Critique 6: Synthetic demand makes the results partly circular** — Severity: 🟠 Major
**Issue:** Ticket data is not open, so the demand model trains on synthetic data, and the simulator also uses that demand. The system is then tested on the same assumptions it was built from. Judges may question the reported gains.
**Suggested fix:** Generate synthetic boardings from a documented model calibrated to published ridership, and publish the generator. In the simulator, run each strategy against demand with added forecast error (for example, ±20% and ±40%), and report how gains change. Include one scenario where the forecast is badly wrong, to show the human approval step and the minimum-frequency rule still protect riders.
**Trade-off:** More simulator runs. These run offline, so they cost only laptop time.

**Critique 7: Scope is large for a hackathon team** — Severity: 🟡 Minor
**Issue:** Four forecast and detection models, an optimiser, control rules, a simulator, a live console, and an LLM layer is a lot for 4 people. Features such as the edit action, rejection-reason learning, electric-bus charge limits, and short-turn suggestions add work but little to the core demo.
**Suggested fix:** Keep one clear core loop: detect, reallocate, explain, approve, and measure. Keep holding as a simulator baseline. Move edit, short-turn, EV charge limits, and threshold learning to a "future work" list. Log rejection reasons, but do not claim that the system learns from them.
**Trade-off:** A smaller feature list. The demo becomes more reliable.

**Critique 8: "Observed passengers left behind" cannot be observed** — Severity: 🟡 Minor
**Issue:** The overcrowding rule uses observed left-behind passengers. Without passenger counters or cameras, the system has no source for this number.
**Suggested fix:** Remove the "observed" condition from the live rule. Report left-behind passengers only as a simulator output, and describe it as estimated.
**Trade-off:** None.

## 5. Strengthened Solution

Keep AduthaBus's core idea: network-level bus reallocation with human approval. Rebuild the delivery around Render's free tier:

- A static React console on a Render static site, with OpenFreeMap tiles.
- One FastAPI web service that loads pre-trained artefacts and runs request-driven cycles on a replay clock.
- One free Render Postgres database used only for the decision log, with CSV export.
- Template explanations instead of a paid LLM.
- All training and heavy simulation done offline on laptops, with results committed to the repository.
- Robustness tests against demand error, to answer the synthetic-data question.

`solution2.md` describes this design in full.

**Alternative approach worth considering:** Run the whole engine in the browser with Pyodide or a TypeScript port, and host only static files on Render. This removes cold starts and server memory limits. It was not chosen because OR-Tools and LightGBM are hard to run in the browser and the team would lose Python tooling.

## 6. Verdict

**Score:** 5/10 as written. The concept is strong (about 8/10), but three critical constraint breaks make it undeployable within the project's limits.

**Top 3 priorities:**

1. Replace the Claude API with template explanations.
2. Split into an offline lane (training, simulation) and a light online lane that fits 512 MB and 0.1 CPU.
3. Make the cycle request-driven with a replay clock, so spin-down does not break the demo.

**Quick validation step:** Deploy a "hello" FastAPI service to Render free that imports pandas, LightGBM, and OR-Tools, loads one model file, and solves a 6-route toy CP-SAT model. Record peak memory, cold-start time, and solve time. This tests the riskiest assumption (that the online lane fits the free instance) in about one hour.
