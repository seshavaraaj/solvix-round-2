# TransitPulse Lite — Frontend Handoff to Person A

| Field | Value |
|---|---|
| Drafted | 2026-09-26 |
| From | Person B (frontend) |
| Covers | [`02-frontend-plan.md`](02-frontend-plan.md) handoff checklist, M0 items |

## 1. Static-site entries for `render.yaml`

Add these three services under `services:`. Replace the API URL with the real Render URL once it exists.

```yaml
  - type: web
    name: transitpulse-operator
    runtime: static
    rootDir: operator
    buildCommand: npm ci && npm run build
    staticPublishPath: dist
    envVars:
      - key: VITE_API_URL
        value: https://transitpulse-api.onrender.com
    routes:
      - type: rewrite
        source: /*
        destination: /index.html

  - type: web
    name: transitpulse-admin
    runtime: static
    rootDir: admin
    buildCommand: npm ci && npm run build
    staticPublishPath: dist
    envVars:
      - key: VITE_API_URL
        value: https://transitpulse-api.onrender.com
    routes:
      - type: rewrite
        source: /*
        destination: /index.html

  - type: web
    name: transitpulse-rider
    runtime: static
    rootDir: rider
    # Render static sites do not include Flutter, so the build clones the stable SDK.
    buildCommand: >-
      git clone https://github.com/flutter/flutter.git -b stable --depth 1 $HOME/flutter &&
      $HOME/flutter/bin/flutter config --enable-web &&
      $HOME/flutter/bin/flutter build web --release --dart-define=API_URL=$API_URL
    staticPublishPath: build/web
    envVars:
      - key: API_URL
        value: https://transitpulse-api.onrender.com
```

**Rider fallback:** if the Flutter build on Render is too slow or fails, B builds locally, commits `rider/web_dist/`, and the entry changes to `buildCommand: ""` and `staticPublishPath: web_dist`.

## 2. Environment variables owned by B

| Variable | Site | When read |
|---|---|---|
| `VITE_API_URL` | operator, admin | build time (Vite inlines it) |
| `API_URL` | rider | build time (`--dart-define`) |

Changing either needs a redeploy of that static site.

## 3. `CORS_ORIGINS`

Local origins the apps use: `http://localhost:5173` (operator), `http://localhost:5174` (admin), `http://localhost:8080` (rider). Add the three `*.onrender.com` static-site URLs after the first deploy.

## 4. What the frontends assume (check against the mock and API)

These are readings of the contract, not new fields. If any is wrong, the fix goes in a `contract/` PR.

| Assumption | Where it matters |
|---|---|
| Network failure or `503` from any endpoint means "server waking"; the app polls `/health` until `status == "ok"`. | All apps |
| `Recommendation.expected_effect` may omit `from_route` (for `add_trip`) or `to_route` (for `release_bus`). | Operator card |
| `GET /recommendations` with no `status` returns all statuses. | Operator filter "All" |
| `POST /clock` with `{"action":"play"|"pause","speed":N}` changes speed without changing play state. | Operator clock bar |
| `GET /decisions` pages are newest first. | Admin decision log |
| `CrowdingReport.lat/lon` is the phone's position when the rider allows location, else the bus's last position. | Rider |
| `GET /buses` without `route_id` returns every bus in the cluster. | Rider map, "on bus" list |

## 5. Before the first deploy

- Run `npm install` once in `operator/` and `admin/` and commit both `package-lock.json` files. `npm ci` fails without them.
- In `rider/`, run `flutter create --platforms=web,android --project-name transitpulse_rider .` once. It adds the missing Android scaffolding and keeps the existing `lib/`, `web/` and `test/` files.
