# TransitPulse fleet admin portal

React 18 + Vite + TypeScript. Routes, fleet per depot, decision log with CSV export. This is the first thing to cut if time runs short (contract §9).

```bash
cp .env.example .env          # VITE_API_URL=http://localhost:8000 (mock server)
npm install
npm run dev                   # http://localhost:5174
npm test
npm run build                 # dist/
```

`src/api/` is a copy of `operator/src/api/`. After any contract change, update the operator copy first and then run:

```powershell
Copy-Item ..\operator\src\api\types.ts, ..\operator\src\api\client.ts src\api\
```
