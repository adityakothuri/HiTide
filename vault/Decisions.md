---
tags: [hitide, decisions]
status: in-progress
updated: 2026-11-07
---

# Decisions

Dated log. Add a new entry at the top when a decision changes the plan. Keep the reason, not just the choice.

## 2026-11-07: Road status thresholds from NWS TADD table

- Thresholds: caution 3 in, closed 6 in, float 12 in, boat 24 in.
- Source: [NWS Turn Around Don't Drown](https://www.weather.gov/safety/flood-turn-around-dont-drown).
- Stored in `road_status_in` in `backend/config/weights.yaml`, not hard-coded.
- Caution at 3 in is our own band. The NWS page does not define it.
- Related: [[Risk Scoring]]

## 2026-11-07: Hand-traced river fallback if Overpass is unreachable

- If every Overpass mirror fails, the build uses a hand-traced Guadalupe River centerline (`RIVER_FALLBACK` in `backend/scripts/build_town_cache.py`).
- Reason: the demo must run offline, and Overpass was unreachable during the first run.
- Related: [[2026-11-07 Town cache build]], [[Flood Simulation]]

## 2026-11-07: Outreach adapter with mock mode because no Photon creds yet

- Every outbound action goes through one adapter. `PHOTON_MODE=mock` logs and streams to the UI. `photon` sends for real.
- Reason: no Photon creds yet. The demo must not depend on Photon.
- Related: [[Photon Outreach]]

## 2026-11-07: Python 3.12 via uv because system Python 3.15 lacks geo and ML wheels

- `backend/.python-version` pins 3.12. `uv` manages the venv and lockfile (`backend/uv.lock`).
- Reason: the system Python is 3.15, which likely has no torch, ultralytics, or osmnx wheels.
- Related: [[Architecture]]

## 2026-11-07: Photon Stable (Spectrum) chosen

- Photon Spectrum (Stable) is the Photon version we use.
- Reason: it is the only version that documents polls, read receipts, and outbound SIP voice on an iMessage line.
- Related: [[Photon Outreach]], [[Data Sources]]

## 2026-11-07: Photon sends go through a Node sidecar
Spectrum's REST OpenAPI has no send or poll endpoint. Only `spectrum-ts` can send. We added `photon-sidecar/` (about 80 lines) exposing `/send` and `/poll`, and it forwards inbound replies to `/api/photon/inbound`. The Python adapter talks to the sidecar.

## 2026-11-07: Demo clock, fast-forward then 1x
At 60x, the 12 s escalation timers would last 0.2 s on screen and cars would teleport. The scenario ramps the flood at 300x to minute 35 (about 7 s), then runs at 1x so the timers and driving are real-time. Suggested by the planner agent.

## 2026-11-07: Two meanings of "moving"
Pre-trip texts skip any driver **on a trip** (`DriverMotion.moving`). The outreach guard blocks text, poll and voice only when the car is **physically moving** (speed ≥ 0.5 m/s). A car stalled in water must still get the "Are you okay?" call.

## 2026-11-07: Est. claims avoided is an estimate
(warned + rerouted) × avg vehicle flood claim × 10% (the assumed share who would have driven into water). The placeholder average is $15k. It needs a source before the pitch.

## 2026-11-07: Move outreach to Photon 2.0 (beta)
The Photon track requires 2.0, and we had built on Stable. 2.0 has a plain REST API (users → spaces → messages), so Python calls it directly. Inbound arrives over Socket.IO, so there's no tunnel. `PHOTON_MODE=mock|stable|photon2`, and Stable stays as the fallback.

## 2026-11-07: Voice = ElevenLabs agent over Photon SIP, set up by script
Voice runs on the Photon SMS number (iMessage lines can't take calls on a shared line). `scripts/elevenlabs_setup.py` creates the agent and imports the number through the API, because the dashboard UI kept changing. The first message is the `{{opening_line}}` variable, since first-message overrides were rejected on SIP calls.

## 2026-11-07: Calls run in the background; voicemail counts as no answer
Call setup takes 10–20 s, so the call never blocks the sim tick. The transcript watcher starts when the call ID arrives. Voicemail detection leaves one message and hangs up, and escalation continues.

## 2026-11-07: Margaret's demo phone = Teammate B
B gets no texts during the demo (B is the moving driver), so B's phone ringing as "Margaret" at step 4 is the live voice moment. Change `demo-d.phone` in `data/drivers.json` to reassign it.

## 2026-11-07: Frontend design system (Checkpoint 1)
- Critical status is magenta-plum `#931566` (hue 321°), not brand red `#B3121F` (hue 355°). Danger is always icon + label + critical color. Brand red means "State Farm" and "selected", never danger.
- Public Sans, self-hosted, so the demo works offline. It's legible on a projector and has an institutional tone.
- The console map has no basemap tiles. It's drawn from our own OSM segments and river on a neutral surface, so it works offline and the water scale is the only saturated color.
- Anti-template review changed: KPI cards → inline counters, shadow cards → bordered sections, dot-only timeline → icon shape + text state, middle-dot meta → written-out phrases. Full table in [[Design System]] §6.
- Frontend work runs in a separate worktree on branch `feat/frontend`, so it doesn't touch the backend agent's tree. (All branches merged to `main` on 2026-11-08.)

## 2026-11-07: Voice "safe" needs the agent's collected status
A transcript regex alone matched "okay... hello?" and voicemail greetings as safe, which closed the case and cancelled the drone. Now the transcript can only escalate. Only ElevenLabs' `driver_status` data collection (prompted as "safe only if they clearly say they are safe and out of the water") can de-escalate. Texts and the app buttons still use the reply parser.

## 2026-11-07: Claims figure = TDI Harvey average paid auto loss
$19,943 (Texas Dept. of Insurance data call, about 203k Harvey auto claims). It's Texas and flood-driven, so it fits Kerrville better than a national comprehensive average (about $2.7k across all comp claims). The 10% "would have driven in" share is still our assumption and is labelled as one.

## 2026-11-08: Hill Country replay of the real July 4, 2025 flood
Area Hunt → Ingram → Kerrville (user choice): rural single-exit communities plus a dense town. The replay uses real USGS gauge series and the real NWS warning times. Camps and RV parks get **generic labels** on screen (user choice). The real event is cited only in the pitch and vault.

## 2026-11-08: Truth vs belief are separate models
Truth is the gauges with the dead Hunt gauge's outages bridged from the downstream gauge, plus modeled ungauged creeks. Belief is **causal**: only readings already reported, never a future or a dead gauge (python-reviewer findings #1 and #2). Drones are the only way truth enters belief. Without this split the demo couldn't show why drones matter.

## 2026-11-08: Exact chokepoints = k-route intersection + cut test
Overview §8.2 defines unavoidable points via the routes. The colleague's analysis uses a remove-one reachability test. We use the routes as a superset and the cut test to make it exact.

## 2026-11-08: Terrain-following flight, not ridge + clearance
Flying at the highest terrain on a leg + 60 m would exceed the 400 ft (122 m) AGL limit over Hill Country valleys. The drones follow the terrain at 80 m AGL and pay climb time instead.

## 2026-11-08: Indirect evidence is capped at "likely"
The overview's additive evidence could reach 0.95 from rain + gauges + model alone. We cap it at 0.85, so only direct evidence (drone, closure, impact point) can say "confirmed".

## 2026-11-08: Information value decays from now when there's no deadline
Without it the planner was indifferent to visiting order and minimized flight time instead of checking the most valuable point first (found by `test_highest_value_per_second_goes_first`).

## 2026-11-08: Area risk score; objective "move low to high"
User request: every area gets a 0–100 risk score (access, water, ground height, vulnerability). People move from low, high-risk ground to high ground: every route-out ends at a destination at least 12 m above the nearest waterway, and areas are listed highest risk first.

## 2026-11-08: Region data is committed
`data/region/hill_country/` is about 12 MB, so the demo is fully offline. The osmnx HTTP cache (`backend/cache/`) is gitignored.

## 2026-11-07: Frontend follows State Farm's public design tokens

- **Context:** the user wanted the UI to read as official State Farm tooling.
- **Decision:** we took the palette, button shapes and header, tab and notification patterns from statefarm.com's published CSS.
- **Limits kept:** we don't use State Farm's logo. The mark is a neutral shield with a waterline, and every surface keeps the "Concept prototype" footer. The demo can look like their tooling without passing as an official product.
- **Demo features added in this round:**
  - An in-app mirror of the HiTide voice call (answer or decline; answering plays the script and lets the driver tap "I'm safe" or "I need help").
  - A lock-screen style banner for the pre-trip text.
  - A presenter control for which persona the phone shows.

## 2026-11-07: Ops console becomes a weather and flood dashboard

- **Context:** the console looked like a dispatch toy (glow, counters, "minutes gained"). The user asked for a professional NWS/Windy-style map.
- **Decision:** full-bleed CARTO Dark Matter map; thin left panel (layer toggles + compact case list); detail only on click; colorbar always visible; time slider at the bottom. State Farm red only in the wordmark.
- **Time source:** one `WxSource` interface. The July 4, 2025 replay (01:00 to 07:30 CDT) is computed in the browser from cached files, so the slider scrubs freely and the demo runs offline. A live source is stubbed (`src/wx/liveSource.ts`) for when the partner's keys and data arrive.
- **Rain:** archived MRMS from the Iowa Environmental Mesonet tile cache. IEM's ramp starts in saturated blue and hid the blue depth layer, so tiles are decoded back to inches and redrawn with an NWS-style ramp (greens to magenta, transparent under 0.01 in). The archived `p1h` tiles use the `p24h` legend scale, not the linear 1-9 in `p1h` image (checked: hourly sums match the 24 h total at Hunt and Kerrville).
- **Flood depth:** the HAND-style model from `sim/hand_flood.py`, run on every cell of a 10 m 3DEP grid (`backend/sim/depth_grid.py`, tested). One PNG per 0.5 m of Kerrville gauge rise; the client picks the frame for the gauge stage at time t. Not a hydraulic model, labelled "modelled".
- **Gauges:** NWS NWPS categories exist only for Hunt (HNTT2) and Kerrville (KRRT2); the other three show gray. A gauge with no reading (Hunt after 05:10) shows dark gray, not a guess.
- **Polish pass (2026-11-08):** rain bins under 0.25 in are partly transparent so widespread light rain doesn't hide the basemap; rain draws from z8 tiles overzoomed with linear resampling (smooth field like radar viewers, not 1 km blocks); the left panel gains an NWS-style river gauge table (ranked by category, stage and trend, click opens the gauge); NWS warning issuance times are marked on the time slider.

## 2026-11-08: Independent HiTide brand in both apps

- **Context:** sid's mobile app and mockups dropped State Farm branding (royal blue, wave mark). The console still used State Farm red.
- **Decision (user):** both apps use the independent HiTide identity, and no State Farm name or logo appears in any UI. Cobalt `#2448E8` replaces the red wordmark and primary buttons. The 2026-11-07 "follows State Farm's public design tokens" decision is superseded for visuals. The pitch can still frame HiTide as an insurer program.
- **Left as is:**
  - The web driver app's Claims tab (wired into the driver flow and its tests). The mobile app is the consumer surface.
  - Backend message templates.

## 2026-11-08: Dashboard = sid's operator shell + map-first Flood monitor

- **Decision (user):** one sidebar shell frames four pages:
  - `/console` Flood monitor (GIS risk map, time bar)
  - `/console/cases` Driver cases (queue, map, detail, after mockup 03)
  - `/console/inspections` (sid's evidence workflow, re-tokened)
  - `/console/sources` (provenance table)
- **Not adopted:** we didn't add deck.gl, Tailwind, shadcn, Zustand or Recharts six hours before submission. MapLibre image sources plus a canvas cover the risk surface.

## 2026-11-08: Risk surface scope

- **Coverage:** the 30 m Hill Country DEM covers Hunt to Kerrville, not the whole county. The legend says "Study area: Hunt to Kerrville".
- **FEMA flood zones** are dropped because they aren't cached offline.
- **SpacetimeDB `risk_grid_frame`** is deferred. Static frames plus the existing replay clock keep clients in sync.
- **Mock-mode feeds** are labelled "Recorded sample, offline demo" on the Sources page, never "Live".

## 2026-11-08: Floating-panel restyle tried and reverted

- **Tried:** frosted floating cards, an icon rail, header chips, a rain histogram, pulsing markers and gauge cards.
- **Outcome:** you rejected it as looking generic and "vibe-coded", so the console went back to the round-4 analyst design.
- **Kept from that round:**
  - The source health bar is removed from Inspections. A "Return to Kerrville" button replaces it while an exercise is loaded.
  - Calmer flooded roads: zoom-scaled width with a thin white casing, softer crimson and amber, and "likely flooded" only from z11.
  - Overlap fixes: the left panel scrolls as one column, gauge names end in an ellipsis, and the attribution stays clear of the detail panel.
  - The road-verification map shows no base field.
  - `index.json` frames carry optional `rain1h_max` / `rain1h_mean`.

## 2026-11-08: Flood monitor runs on the Hill Country region system

- **Why:** you found the monitor hard to read (conflicting colours, many moving dots). You asked for three things: who is in a tough spot, the area's critical points (computed, not hardcoded), and drones touring those points.
- **What:** `/console` now reads the backend region pipeline. Nothing about the points is hardcoded; they come from the OSM roads, the 3DEP terrain and the waterways.
  - **Critical points:** `population/nodes.py` and the `critical/` cut tests and ranking.
  - **Areas** with their status and rescue (boat or truck).
  - **People:** the 251-user `safety/` danger ladder.
  - **Drones:** the 3-drone fleet with priority tours (`critical/loop.py`, `drone/planner.py`).
  - **Code:** the frontend lives in `frontend/src/region/` (polling hook plus tested `derive.ts`) and `map/regionLayers.ts`.
- **One clock:** the backend July 4 replay (`POST /api/demo/start?scenario=hill_country&speed=60`) drives the time bar. The weather and risk layers follow `sim_time`.
- **Map colours:**
  - red: in danger, cut off or flooded
  - amber: at risk or likely flooded
  - grey: watched point
  - blue: drones and their routes
  - The risk surface sits underneath at 35 %. Gauges, rain and flooded roads are behind a Layers button.
- **Kept:** Driver cases and `/present` still run the Kerrville town scenario.
