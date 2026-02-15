# frontend2

Next.js + React + shadcn-style UI for the Detour dashboard.

## Stack
- Next.js (App Router)
- React + TypeScript
- Tailwind CSS v4
- shadcn-style component setup (`components.json`, `lib/utils.ts`, `components/ui/*`)
- React Three Fiber (`@react-three/fiber`, `@react-three/drei`, `three`)

## Globe: Real Earth Mapping

### Texture asset
Place a local equirectangular Earth texture at:

`public/textures/earth/blue-marble-day.jpg`

Recommended source: NASA Blue Marble (Visible Earth collection).

### Coordinate frame convention
- Earth mesh is rendered in an Earth-fixed frame.
- `+Y` = north pole.
- Longitude `0°` = prime meridian at `+X`.
- Positive east longitudes map toward `-Z`.

### Geodetic conversion
Implemented in `lib/geo.ts`:

- `EARTH_RADIUS_KM = 6378.137`
- `r = 1 + altKm / EARTH_RADIUS_KM`
- `x = r * cos(latRad) * cos(lonRad)`
- `y = r * sin(latRad)`
- `z = -r * cos(latRad) * sin(lonRad)`

### Object placement pipeline
`components/globe-view.tsx` maps API objects in this order:
1. Primary: backend `lat`, `lon`, `alt_km` -> geodetic conversion
2. Fallback: backend ECI `position` -> previous scaling path

This keeps compatibility while aligning markers to real coastlines when geodetic fields are present.

## Run
```bash
cd frontend2
npm install
npm run dev
```

Open `http://localhost:3000`.
