# AduthaBus Lite — Frontend Implementation Plan (Person B)

| Field | Value |
|---|---|
| Drafted | 2026-09-25 |
| Owner | Person B — Frontend |
| Scope | Operator console (React), fleet admin portal (React), rider app (Flutter Web + optional sideload APK), three Render static sites |
| Contract | [`00-shared-contract.md`](00-shared-contract.md) — all JSON shapes and endpoints live there |
| Partner plan | [`01-backend-plan.md`](01-backend-plan.md) (Person A) |
| Source design | [`../solutions/solution2.md`](../solutions/solution2.md) §6.10, §8, §11 |

**Mock-first rule:** build every screen against the mock server (contract §7) first. At each milestone, only switch `API_URL` to the real API and fix gaps. Never wait on Person A.

**Rule:** do not rename or reshape fields in UI code. If a field is missing or wrong, open a `contract/` PR (contract §10).

---

## Stack (all free / open source)

| Layer | Operator console + admin portal | Rider app |
|---|---|---|
| Framework | React 18 + Vite + TypeScript | Flutter (stable), Web target |
| Data fetching | TanStack Query (polling, caching, retries) | `http` package + simple `Timer` polling |
| Routing | React Router | `go_router` (or plain `Navigator`, 3 screens only) |
| Map | MapLibre GL JS + OpenFreeMap style (`https://tiles.openfreemap.org/styles/liberty`) | `flutter_map` + `vector_map_tiles` with OpenFreeMap style |
| Charts | Recharts | — |
| UI kit | Plain CSS or a free component lib (e.g. Mantine) | Material 3 |
| Storage | `sessionStorage` for JWT | `shared_preferences` for device UUID + rider token |
| Tests | Vitest + React Testing Library; Playwright smoke (optional) | `flutter test` widget tests |

No paid map keys, no paid analytics, no paid hosting.

---

## F0 — Setup → **M0**

Tasks
1. Scaffold `operator/` and `admin/` with `npm create vite@latest -- --template react-ts`. Admin dev port `5174` (set in `vite.config.ts`).
2. Scaffold `rider/` with `flutter create --platforms=web,android rider`. Dev: `flutter run -d chrome --web-port 8080 --dart-define=API_URL=http://localhost:8000`.
3. API client layer, written by hand from contract §5–§6:
   - `operator/src/api/types.ts`, `operator/src/api/client.ts` (fetch wrapper: base URL from `import.meta.env.VITE_API_URL`, adds `Authorization`, parses `{"error":{...}}`, maps `503 loading` to a "waking" state, `401` → back to login).
   - `admin/src/api/` = copy of the operator client (same types). Keep them identical; diff them when the contract changes.
   - `rider/lib/api/models.dart` (`fromJson`/`toJson`), `rider/lib/api/client.dart`.
4. Run the mock server (`uvicorn mock.server:app --port 8000`) and show fixture data in each app.
5. Give Person A the static-site build commands for `render.yaml` (contract §11 and F5 below). Confirm SPA rewrite `/*` → `/index.html` for both React sites.

Done when: all three apps build and show mock data locally.

---

## F1 — Operator console shell (against mock)

Files: `operator/src/{App.tsx, pages/, components/, hooks/}`

1. **Wake-up screen** (`components/WakeUp.tsx`): poll `GET /health` every 3 s; show "Starting server (about 1 minute)…" until `status == "ok"`. Show it again whenever any call returns `503 loading`.
2. **Login** (`pages/Login.tsx`): `POST /auth/login`; store token in `sessionStorage`; reject non-`operator` role.
3. **Layout:** map (left/center), side panel with tabs *Routes*, *Recommendations*, *Results*; top bar with clock + feed health.
4. **Map** (`components/NetworkMap.tsx`): MapLibre + OpenFreeMap. Route shapes as a GeoJSON line layer coloured by `Route.color`. If the style fails to load, fall back to a blank background style with only route and bus layers (solution2 §6.10.1).
5. **Clock controls** (`components/ClockBar.tsx`): `GET /clock`, `POST /clock` for play / pause / speed ×1, ×10, ×30 / jump to scenario (dropdown with the four scenarios). Re-read clock after reconnect.

Done when: login → map with routes → clock controls work on mock.

---

## F2 — Operator live data → consumes **M1**

Endpoints: `/state`, `/routes`, `/clock`

1. `useStateQuery` hook: poll `GET /state` every 2 s while playing, every 10 s while paused.
2. **Bus layer:** circle per `Bus`, colour by `load_factor` (< 0.6 green, 0.6–1.0 amber, > 1.0 red), grey + dashed outline if `dark`. Popup: route, load %, delay, last seen.
3. **Route health table** (`components/RouteHealthTable.tsx`): one row per route-direction, four flag chips; hover/tap shows `evidence` and `confidence`. Click a row → map zooms to the route.
4. **Feed health badge:** `buses_reporting / buses_expected`, `mode` (replay/live).
5. Switch `VITE_API_URL` to the real API. Run the M1 joint test with Person A.

Done when: M1 joint test passes (contract §9).

---

## F3 — Recommendations → consumes **M2**

Endpoints: `/cycle`, `/recommendations`, `/decisions`, `/decisions.csv`

1. Call `POST /cycle?t=` when the clock advances ≥ 15 simulated minutes and on a manual "Run cycle" button. Show a spinner (solve can take ~5 s).
2. **Recommendation queue** (`components/RecommendationCard.tsx`): action icon, routes, window, `explanation`, before/after numbers from `expected_effect`, `confidence`, `deadhead_km`, `solver` badge ("greedy" in grey).
3. **Approve** → `POST /decisions`. **Reject** → modal with required `reason` (enum from contract §5) + optional note. Handle `409` (already decided) by refreshing the list.
4. Filter by status; expired cards collapse.
5. **Export CSV** button → download `GET /decisions.csv` (fetch with token, save as blob).

Done when: M2 joint test passes: event-surge card appears, approve row appears in CSV.

---

## F4 — What-if and Results → consumes **M3**

Endpoints: `/whatif`, `/results`

1. **What-if panel** on each pending card: button "Simulate"; `POST /whatif`; progress state up to ~10 s with "Simulating 2 hours…"; timeout at 30 s with retry.
2. Show `without` vs `with` metrics side by side and a line chart of `series` (load with / without).
3. **Results tab** (`pages/Results.tsx`): from `GET /results`:
   - Grouped bar chart: avg wait by scenario × strategy (error level 0).
   - Robustness chart: AduthaBus gain vs baseline across error levels (0, 0.2, 0.4, missed surge).
   - Table of all metrics with directions (lower/higher is better, solution2 §6.11).

Done when: M3 joint test passes on Render.

---

## F5 — Rider app (Flutter)

Start shell after F1 against mock; wire real data after **M1**; crowding + alerts after **M4**.

Endpoints: `/health`, `/routes`, `/buses`, `/eta`, `/alerts`, `/auth/device`, `/crowding`

Screens (keep to three, solution2 §12 risk on bundle size):
1. **Map screen:** route cluster, live buses (poll `/buses` every 5 s), colour by load. Tap a stop → ETA sheet from `/eta`.
2. **My routes:** pick routes to follow (saved locally); alerts list from `/alerts?route_id=`.
3. **I'm on this bus:** pick a nearby bus (from `/buses`, sorted by distance to the phone's location if permission given, else by route) → three big buttons **Crowded / OK / Empty** → `POST /crowding`. Show "Thanks" on `201`, "Already reported, try in a few minutes" on `429`.

Device identity:
- On first run, generate a UUID, store in `shared_preferences`, call `POST /auth/device`, store the rider token. Refresh token on `401`.
- No login screen.

Wake-up: same `/health` polling pattern as the operator console, rider-friendly text.

Build and deploy:
- Web build: `flutter build web --release --dart-define=API_URL=$API_URL`.
- Render static sites do not include Flutter. Build command for `render.yaml` (Person A adds it):
  ```
  git clone https://github.com/flutter/flutter.git -b stable --depth 1 $HOME/flutter && $HOME/flutter/bin/flutter config --enable-web && $HOME/flutter/bin/flutter build web --release --dart-define=API_URL=$API_URL
  ```
  Publish directory: `build/web`. If the Render build is too slow or fails, fallback: build locally and commit the output to `rider/web_dist/`, and set publish directory to `rider/web_dist` with an empty build command.
- PWA: keep Flutter's generated `manifest.json`; set app name, icons, theme colour so "Add to Home Screen" works.
- Optional APK for the demo: `flutter build apk --release --dart-define=API_URL=...`, sideload. No Play Store (fee breaks the zero-budget rule).
- Test first load on the actual demo phone; target < 5 s on 4G after the API is awake. If the bundle is too heavy, trim packages and keep icon tree-shaking on (default in release builds); last resort per solution2 §12 is a small React PWA.

Done when: M4 joint test passes: "Crowded" tap on Route 534 shows up on the operator map.

---

## F6 — Fleet admin portal (cut first) → consumes **M4**

Endpoints: `/auth/login`, `/admin/routes`, `/admin/fleet`, `/decisions`, `/decisions.csv`, `/routes`

1. Login (reject non-`admin` role), same client as operator.
2. **Routes page:** table of routes; edit form for name, depot, `min_headway_min`, colour; stops shown read-only (from GTFS). `PUT /admin/routes/{id}`.
3. **Fleet page:** per depot `fleet_size`, `reserve`, `out_of_service`. `PUT /admin/fleet/{depot_id}`. Validate `reserve + out_of_service ≤ fleet_size` client-side.
4. **Decision log:** paginated `GET /decisions`, Export CSV.
5. **Cut path:** if Person A announces the admin cut (backend plan B6 step 6), build only a read-only page listing routes and fleet, or drop the portal and mention it in the pitch.

---

## F7 — Polish → **M5**

1. Responsive checks: operator console at 1366×768 and projector resolution; rider app at 360×800.
2. Empty, loading, error, and `503` states on every screen.
3. Accessibility basics: load colours also shown as text/percent; buttons ≥ 44 px on rider app.
4. Demo run-through (solution2 §11) with Person A on Render URLs. Keep a browser tab on the operator console open 2 minutes before judging to wake the API.
5. Screenshots for the deck.

---

## Testing

| Level | What |
|---|---|
| Unit | API client error mapping (401, 409, 429, 503); load colour thresholds; reject-reason validation |
| Component | RecommendationCard approve/reject flow against mock |
| Flutter widget | crowding buttons send the right `level`; 429 message |
| Smoke | each milestone: load app on Render URL, complete the joint test in contract §9 |

## Risks owned by B

| Risk | Mitigation |
|---|---|
| Cold start looks like a broken app | Wake-up screen on every app; `503 loading` handling |
| OpenFreeMap tiles down | Blank-style fallback with route + bus layers |
| Flutter not available on Render build | Clone SDK in build command; fallback to committed `web_dist/` |
| Flutter Web bundle slow on phone | Three screens only; test on demo phone; React PWA fallback |
| Backend late | Mock-first rule; fixtures cover every endpoint |

## Handoff checklist (what Person A needs from B)

- [ ] **M0:** static-site build commands, publish dirs, and env var names for `render.yaml`
- [ ] **M0:** final list of static-site URLs for `CORS_ORIGINS` (after first deploy)
- [ ] **M1–M4:** confirmation that each joint test passes on Render, or a list of contract gaps found (as `contract/` PRs)
- [ ] Any extra endpoint or field the UI needs, raised as a `contract/` PR — never worked around in UI code
- [ ] **M4:** decision on admin portal scope (full / read-only / cut), agreed with A
