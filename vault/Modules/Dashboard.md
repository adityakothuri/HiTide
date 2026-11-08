---
tags: [floodwatch, module, frontend]
status: in-progress
updated: 2026-11-07
---

# Dashboard

The frontend lives in `frontend/` (React + Vite + TS) and has two surfaces plus a presentation mode:

- **Driver app**: see [[Driver App]].
- **Operations console**: case queue, map, case detail with the drone panel and "minutes gained". Built in Phase 4.
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

## Data layer

- `src/data/provider.ts`: the `DataProvider` interface, shared by:
  - `WsProvider`: live, reconnects with jittered backoff
  - `MockProvider`: replays `src/demo/recording.json`, a real recording of the backend's 7-step demo (232 events) re-timed to now
- `src/state/reducer.ts`: a pure reducer over every WS event type. A snapshot replaces everything. Stale `seq` values are ignored. Local events use `seq: -1`.
- `src/state/cases.ts`: urgency sort, filters, severity, step labels.
- Tests: 73 vitest specs, written test-first (see [[Tooling]]).

## Related

- [[Architecture]], [[Driver App]], [[Design System]]
