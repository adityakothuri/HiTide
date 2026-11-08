---
tags: [hitide, frontend, design, audit]
status: checkpoint-1
updated: 2026-11-08
---

# UI audit (Checkpoint 1, ops dashboard refinement)

This is Phase 1 of the brief to make the ops dashboard map-first and professional, refining the existing UI rather than rewriting it. It covers state after merging `feat/frontend` (incl. sid's `1ed7a00`) into `feat/safety-core` (`a60087d`). No app code was changed.

Screenshots: `screenshots/audit-{1440,1280}-*.png`

| View | Shots |
|---|---|
| `/texas` | texas |
| `/console` | console-inspections, console-flood-monitor, console-exercise |
| `/present` | present-05s, present-30s, present-65s |
| `/driver` | driver |
| `/gallery` | gallery (full page) |

## 0. Blockers found before any styling

1. **The wx map dashboard isn't on `/console`.** `App.tsx:62` sends `/console` to sid's `<Operations/>`, a light, royal-blue inspections page. The real map console (`console/Console.tsx`) only renders inside `/present` (`present/Present.tsx:35`). The `route()` case at `App.tsx:39` is dead code, and so is the Index page, because `''` goes to TexasMonitor.
2. **`/console` shows an error state.** Operations polls `/api/evidence/state`, which no backend branch serves (404). The page says "Evidence service needs attention" and stays empty, even after clicking "Load exercise".
3. **`/texas` shows an error state.** The running backend predates `/api/feeds/recent`. Restarting it fixes this.

**Decision needed (teammates own `frontend/`):**
- Which route hosts the refined map console? Proposal: move the wx Console back to `/console` and move Operations to `/inspections`.
- Does sid's inspections UI get a backend endpoint, or is it out of scope for the demo?

## 1. What works and must be kept

- **Data layer:**
  - `wx/` (`WxSource`, `useWx`, `replaySource`, `liveSource` stub, `category.ts`, `time.ts`): the July 4, 2025 replay runs in the browser and scrubs freely offline.
  - `data/provider.ts`: WS and Mock providers.
  - `state/reducer.ts` and the store, which `/present` uses to share one stream between phone and console.
- **Map plumbing:**
  - `map/useMlMap.ts` already inserts data under the first label layer.
  - `map/wxLayers.ts` already draws only closed and likely-flooded roads, flat, with no casing.
  - Offline basemap fallback after 4 s.
- **Weather layers:**
  - MRMS 1 h and 24 h tiles, recolored to an NWS ramp with low bins translucent, smooth at overzoom.
  - Modelled depth frames per 0.5 m of rise (10 m 3DEP HAND).
  - Five USGS gauges with NWS categories; a gauge with no reading shows gray instead of a guess.
  - NWS warning ticks on the time slider.
- **Layout bones of the wx Console:** thin left rail (layers, gauge table, cases), always-visible combined legend, bottom time slider, detail only on click, and attribution line. This already matches about 70 % of brief §3.
- **Interactions:** gauge and road click opens FeatureDetail with a sparkline; case click opens Detail with drone and vision panels; play, step and scrub; Shift+D presenter panel.
- **Already removed by the colleague:** glow, dollar counters, and the "minutes gained" hero in the console. There's no `text-shadow` or `line-blur` anywhere.
- **Tooling:** `npm run contrast` (WCAG check of tokens), stylelint no-hex rule, vitest, and the Playwright e2e specs.

## 2. Visual problems

Evidence is file:line, from the component scan. Each item maps to brief §8/§10.

| # | Problem | Where | Brief |
|---|---|---|---|
| 1 | **Navy/dark theme everywhere on the map console.** `data-theme="dispatch"` with `--d-bg #0e1620` is used in Console, TopBar, Present, MapView and EvidenceMap, and the basemap is hard-coded to `'dark'` (`MapView.tsx:81`). | Console.module.css:8, TopBar.module.css:7, Present.module.css:6 | §2.1, §8 |
| 2 | **Three themes, three fonts, five palettes.** `/console` is royal blue on white (`--ops-*`, system-ui) with a navy map embedded. `/texas` is State Farm red (Source Sans). `/present` is navy (IBM Plex). | tokens.css, ops.module.css:2-12, EvidenceMap.tsx:154 | §2.2, §2.3 |
| 3 | **No continuous data field.** Rain shows as blocky 1 km bins, depth only near the river, and there's no risk surface. This is the centerpiece the brief asks for. | n/a | §4 |
| 4 | **The legend is a stacked block of four keys mid-map.** It covers the map (bottom center in `present-65s`), has no vertical colorbar, and doesn't change with the base field. | Colorbar.tsx | §4.5 |
| 5 | **All layers on at once.** Rain, depth, gauges and roads are all checkboxes, with no "one base field at a time" rule and no opacity control. | LayerPanel.tsx | §3 |
| 6 | **Uppercase, letter-spaced section labels.** "LAYERS", "RIVER GAUGES", "CASES" and "REPLAY". | LayerPanel.module.css:11, GaugeTable.module.css:14, Queue.module.css:16, Detail.module.css:126, TimeSlider.module.css:109 | §2.3, §10 |
| 7 | **Oversized type, off the scale.** Operations h1 is 34 px/800 and the road title 26 px/800. TexasMonitor metrics are 30 px. Gallery shows "14 minutes gained" at 44 px. The type scale goes up to 44 px and there are 100+ raw px font sizes. | ops.module.css:251, :687, Operations.module.css:40, Gallery.tsx:59 | §2.3, §6 |
| 8 | **Pills and ad-hoc radii.** Buttons, badges, filter counts and ops chips are pills. `--ops-radius` is 14 px, and other places use 5, 9 or 12 px. | Button.module.css:9, StatusBadge.module.css:7, ops.module.css:519,635 | §2.3 |
| 9 | **Five different "simulated" markers.** The TopBar "Simulated" box, RoadDetail chip, "Synthetic exercise" badge, "Simulated thermal"/"Sample image" tags, and the Detail footnote. | TopBar.tsx:77, RoadDetail.tsx:105, SourceHealth.tsx:56, VisionPanel.tsx:43 | §8 |
| 10 | **Raw colors outside the tokens.** Hex in TexasMonitor and EvidenceMap, plus many `rgb(255 255 255 / N%)` literals in console CSS. | TexasMonitor.tsx:105, EvidenceMap.tsx:57, Detail.module.css:9 | §2.2 |
| 11 | **Glow-like halo and heavy shadows.** The amber 16 px selection halo at 0.28 opacity, and black drop shadows on map callouts. | EvidenceMap.tsx:50, EvidenceMap.module.css:111,120,149 | §2.4 |
| 12 | **"Drone vs crew" race bars with a hard-coded 17 min crew ETA.** This is the "minutes gained" idea again in another form. | DronePanel.tsx:27 | §8 |
| 13 | **Gauge dots are 12 px gray rings with dark fills.** Their category colors barely show, and below-action gauges look identical to gauges with no data. | MapView / floodLayers | §5 |
| 14 | **The outreach log and case timelines repeat each other inside Detail.** | Detail.tsx | §8 |
| 15 | **No county boundary or outside mask.** The map extent is just a crop of the basemap. | n/a | §2.4 |
| 16 | **Missing states.** There's no stale (amber timestamp) state, no keyboard (arrows, Space, Esc, `/`), and no search on the map console. | n/a | §7 |

## 3. Component plan

Actions: **keep** = as is; **restyle** = same logic, new tokens and CSS; **merge** = combine into another component; **delete** = drop from the console.

| Component | Action | Notes |
|---|---|---|
| `wx/*` (source, hooks, types, category, time) | keep | Add a `risk` field kind alongside `rain` and `depth` |
| `map/useMlMap.ts`, `map/wxLayers.ts` | keep | Take a basemap argument: Positron (light default) or Dark Matter |
| `map/basemap.ts` | restyle | Light = Positron (it's Voyager now), dark = Dark Matter; drop navy |
| `console/Console.tsx` | restyle | New grid: 48 px header, 280 px left, map, 360 px detail when selected, 56 px time bar; light theme |
| `console/TopBar.tsx` | restyle | Wordmark, county, active warning with expiry, updated time (amber when stale). Drop the "Simulated" box |
| `console/LayerPanel.tsx` | restyle | Radios for the base field (risk/rain/depth), checkboxes for gauges and roads, opacity slider, sentence case |
| `console/GaugeTable.tsx` | merge | Fold into the Gauges row as an expandable list, or into the detail panel. The left panel stays layers + cases |
| `console/Queue.tsx` | restyle | Compact case rows (status icon + label, name, age), "No open cases" empty state |
| `console/Colorbar.tsx` | restyle | Vertical 12×160 px colorbar, bottom-left, for the active base field only. Overlay keys go in small swatches in the layer list |
| `console/TimeSlider.tsx` | restyle | 56 px bar: play, scrubber, past + forecast span, time label, warning ticks kept. Sentence case |
| `console/MapView.tsx` | restyle | Light basemap, county outline + outside mask, risk image source, 10 px gauge circles with a white stroke, scale control |
| `console/Detail.tsx` | restyle | Sectioned label/value rows; case timeline absorbs the outreach log (activity log behind a toggle); max 24 px |
| `console/FeatureDetail.tsx` | restyle | Gauge stage chart; segment evidence list. New critical-point and node sections |
| `console/DronePanel.tsx` | restyle | Keep commands and status; **delete** the race bars and hard-coded crew ETA |
| `console/VisionPanel.tsx` | restyle | Thumbnail + verdict; one small "demo" tag only where the image is synthetic |
| `console/caseInfo.ts` | keep | |
| `evidence/Operations.tsx` + `ops/*` (sid) | keep, move | Move to its own route, unchanged until there's a backend (§0). Swap `EvidenceMap`'s dark map for the shared light one when Phase 2 lands |
| `evidence/TexasMonitor.tsx` | keep | Statewide view, out of scope; later swap its hex values for tokens |
| `present/Present.tsx` | restyle | Neutral page background instead of navy; embeds the refined console |
| `ui/Button`, `StatusBadge`, `FilterTabs` | restyle | 4 px radius instead of pills; brand red only on the primary button |
| `ui/States.tsx`, `Tip`, `Toast`, `Timeline`, `Banner`, `Card` | keep | Reuse for loading, empty, error and stale states |
| `ui/Counter.tsx` | delete (console) | No metric counters on the console |
| `gallery/Gallery.tsx` | restyle | Replace the "minutes gained" sample text and the wrong "Public Sans" label |
| `driver/*` | keep | Driver app is out of scope for this brief |

## 4. Stack reality check (brief §9 vs repo)

- **Missing from `package.json`:** deck.gl, zustand, tailwind, shadcn, recharts and TanStack Table. The repo already uses MapLibre, Radix, Lucide, CSS modules and vitest.
- **Recommendation:** add nothing. Render the risk grid as a MapLibre `image` source drawn from a canvas, keep CSS modules locked to tokens, and draw the gauge chart as the existing SVG sparkline. Keeping the dependency list unchanged is safer six hours before submission.
- **SpacetimeDB:** only appears in `mobile/` and a mockup prompt. Defer `risk_grid_frame`; static `public/grids/` frames plus the existing replay clock keep clients in sync.
- **FEMA flood zones:** not cached, and the demo is offline. Drop that factor and say so on the legend's "about this index" note.
- **Grid extent:** `data/town/dem10.npz` is the town DEM. Use the Hill Country region DEM (`data/region/hill_country/`) if it covers the county; otherwise clip the index to the DEM extent and label it.

## 5. Phase plan (planner agent, cut line marked)

1. **P2, about 1.5 h:** tokens (8-step gray, one red, separate data scales), Positron/Dark Matter switch, layout grid, radio layer panel, status icon + label.
2. **P3, about 3 h:** risk grid in Python with TDD (HAND + distance to waterway + MRMS; 75 m; `config/risk_grid.yaml`; Float32 `.bin` + `index.json`), then in TS with TDD: `risk/grid.ts`, `risk/turbo.ts`, `risk/readout.ts`, colorbar `ticks()`. Canvas image source under labels, county mask, opacity 0.7, scale bar.
3. **P4, about 1.5 h:** gauge circles, critical-point diamonds, drone arrows; detail sections; compact case list.

**Cut line.** Below it:

4. **P5:** time bar restyle (cheap, so do it above the line if possible); crossfade.
5. **P6:** states, keyboard (arrows, Space, Esc), aria.
6. **P7 (never cut):** final screenshots, vault, build and tests.

**Cut order if time slips:** SpacetimeDB, FEMA, live-evidence factor, crossfade, search, forecast span, dark theme, bilinear (fall back to `raster-resampling: linear`).
