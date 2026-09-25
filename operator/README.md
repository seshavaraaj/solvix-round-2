# AduthaBus operator console

React 18 + Vite + TypeScript. Map (MapLibre + OpenFreeMap), route health, recommendation queue with what-if, results charts.

```bash
cp .env.example .env          # VITE_API_URL=http://localhost:8000 (mock server)
npm install
npm run dev                   # http://localhost:5173
npm test                      # Vitest + React Testing Library
npm run build                 # dist/
```

Start the mock API from the repo root first: `uvicorn mock.server:app --port 8000`.

- API types and client: `src/api/`. Keep them identical to `admin/src/api/`, and change the contract before changing a field.
- Render settings: see `.reports/implementation/03-frontend-handoff.md`.
