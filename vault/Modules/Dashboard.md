---
tags: [hitide, module, frontend]
status: in-progress
updated: 2026-11-08
---

# Dashboard

The frontend lives in `frontend/` (React + Vite + TS) and has two surfaces plus a presentation mode:

- **Driver app**: see [[Driver App]].
- **Operations console** (2026-11-08): one operator shell (`src/shell/AppShell.tsx`) with four pages:
  - `/console`: Flood monitor. A map-first GIS view: flood risk, rainfall or modelled depth as the one base field; gauges and roads as overlays; an opacity slider; a vertical colorbar; the scale bar; a time bar over the July 4, 2025 replay; and a hover readout on the risk surface (value, band, top two factors).
  - `/console/cases`: Driver cases. Open/Resolved tabs, the map, and case detail (status, drone, vision, activity, responder summary). The most urgent open case is selected automatically.
  - `/console/inspections`: sid's evidence workflow inside the shell. It needs `/api/evidence/state`.
  - `/console/sources`: every input with provider, use, status (icon + label) and freshness.
- **Presentation**: `/present` puts the phone on the left and the console on the right, both on one store.

Design tokens and wireframes: [[Design System]]. Contract: `docs/api-contract.md` (plus "Proposed additions (frontend)").

## Run

```
cd frontend
npm install
npm run dev          # http://localhost:5173 (proxies /api, /ws, /static to :8000)
npm test             # vitest: reducers, driver flow, formatting
npm run contrast     # WCAG check of token pairings
npm run e2e          # Playwright screenshots
```

URL modes: `?mode=live` uses the backend only. `?mode=mock` replays the recorded demo offline. With no mode, it tries live and falls back to offline after 2.5 s. When the fallback happens, an "Offline demo data" chip shows.

## Keyboard

On the map pages:
- Left/right arrows step time by 5 min.
- Space plays or pauses.
- Esc closes the detail panel.
- `/` focuses the case search.
- Up/down arrows move through the case list.

## Risk surface (client)

The modules live in `src/risk/`, all pure and unit-tested:
- `grid.ts` validates `index.json`, decodes the Float32 and factor frames, and does bilinear sampling.
- `turbo.ts` holds the ramp and the alpha fade.
- `bands.ts`, `ticks.ts` and `readout.ts` produce the bands, colorbar ticks and hover readout.
- `paint.ts` upsamples 2× with bilinear interpolation and NaN masking.

`useRiskGrid` fetches the frame at or before t and prefetches the next. `map/riskLayer.ts` paints it into one of two MapLibre image sources, which crossfade over 350 ms (no fade under reduced motion), under the labels. It also draws the study-area outline and dims everything outside it. Data comes from [[Risk Surface]].

## Data layer

- `src/data/provider.ts`: the `DataProvider` interface, shared by:
  - `WsProvider`: live, reconnects with jittered backoff
  - `MockProvider`: replays `src/demo/recording.json`, a real recording of the backend's 7-step demo (232 events) re-timed to now
- `src/state/reducer.ts`: a pure reducer over every WS event type. A snapshot replaces everything. Stale `seq` values are ignored. Local events use `seq: -1`.
- `src/state/cases.ts`: urgency sort, filters, severity, step labels.
- Tests: 73 vitest specs, written test-first (see [[Tooling]]).

## Related

- [[Architecture]], [[Driver App]], [[Design System]]
