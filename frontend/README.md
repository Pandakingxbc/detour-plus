# frontend

Next.js dashboard for Detour with a local orbital-data backend (no separate API service required).

## Stack
- Next.js (App Router)
- React + TypeScript
- Tailwind CSS v4
- React Three Fiber (`@react-three/fiber`, `@react-three/drei`, `three`)
- `satellite.js` for TLE parsing + SGP4 propagation

## Backend API (Next.js routes)
All routes run in Node runtime and use in-memory caching.

- `GET /api/tle?norad=<id>`
  - Fetches + caches target TLE and debris-group TLE text from CelesTrak.
- `GET /api/target?norad=<id>`
  - Returns target details for the left panel (orbit class, altitude, inclination, updated time, TLE lines).
- `GET /api/orbit?norad=<id>&minutes=<N>&stepSec=<S>`
  - Returns propagated target orbit points.
- `GET /api/debris?limit=<N>`
  - Returns sampled debris positions (bounded for performance).
- `GET /api/feed?norad=<id>&horizonHours=<H>&stepSec=<S>&maxEvents=<K>`
  - Returns CDM-like conjunction events with TCA/miss/risk.
- `GET /api/active-threat?norad=<id>`
  - Returns top-ranked threat from the generated feed.
- `GET/POST /api/constraints`
  - Stores and returns applied planner constraints; feed cache clears on Apply.

## Caching and guardrails
- TLE cache: ~10 minutes
- Feed cache: ~45 seconds
- Debris cap: bounded (default max 1000)
- Feed defaults: 24h horizon, coarse step for demo-safe performance

## Globe texture
Place your Earth image here:

`public/textures/earth/blue-marble-day.jpg`

## Run
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.
