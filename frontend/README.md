# HiTide frontend

React 19 + Vite + TypeScript. Driver app, ops console and presentation mode for HiTide (concept prototype).

```bash
npm install
npm run dev          # http://localhost:5173  (/present, /driver, /console, /gallery)
npm run sync-wx      # copy ../data/wx (rain, depth, gauges) into public/wx; WX_SRC=<path> to copy from another checkout
npm test             # vitest: reducer, screen logic, formatting, geo
npx playwright test  # e2e: full 7-step demo plus screenshots into ../vault/Experiments/screenshots
npm run build        # type check + production build
npm run lint:css     # stylelint (hex colors are only allowed in src/styles/tokens.css)
npm run contrast     # WCAG contrast check of every documented token pair
```

- **Data:** `src/data/` has one `DataProvider` interface with two implementations. `WsProvider` talks to the backend through the Vite proxy (`/api`, `/ws`, `/static` → `VITE_BACKEND_URL`, default `http://localhost:8000`). `MockProvider` replays `src/demo/recording.json`, a recording of the backend's own scripted demo, re-timed to now.
- **Maps:** `src/map/` puts MapLibre on top of CARTO GL styles: dark-matter for the console, voyager for the phone. It tunes the style, draws our flood layers under the street labels, and falls back to `public/town/*.geojson` if the tiles are unreachable (`e2e/maptest.spec.ts` checks both paths).
- **State:** `src/state/` is a pure reducer over the WS events (`reducer.ts`), plus UI-only flags (`store.ts`).
- **Design:** tokens in `src/styles/tokens.css` follow State Farm's public web palette (red `#D62311`, warm grays, link blue `#0073A8`). Critical status uses a separate magenta-crimson with an icon and a label, never brand red. See `vault/Design System.md`.
- No State Farm logo is used. Every surface carries "Concept prototype. Not an official State Farm product."
