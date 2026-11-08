---
tags: [floodwatch, home, status]
status: in-progress
updated: 2026-11-08
---

# State Farm Flood Watch

> **Current integration:** see [State of the Union](../docs/STATE_OF_THE_UNION.md)
> and [[2026-11-07 Evidence milestone]]. The evidence-to-inspection workflow now
> has MongoDB persistence, an operations console, and a verified synthetic feedback
> loop. Legacy phase notes below retain their original driver-rescue scope.

Protect opted-in State Farm drivers in flash floods. Kerrville, TX on the Guadalupe River. Submissions close **Sun Nov 8, 12:00 PM CT**.

> [!note] How to read this vault
> Start with [[Problem]] and [[Architecture]]. Stage notes describe behavior. Module notes link to the code that implements each piece. Decisions and experiments record why things are the way they are.

## Map of content

- Why: [[Problem]] · [[Pitch]] · [[Privacy and Consent]]
- How it works: [[Architecture]] · [[Stage 1 Pre-trip]] · [[Stage 2 En route]] · [[Stage 3 Stopped in water]]
- Frontend: [[Design System]] · [[Driver App]] · [[Dashboard]] · screenshots in `Experiments/screenshots/`
- Modules: [[Per-User Danger]] · [[Live Observations]] · [[Critical Point Drones]] · [[Flood Simulation]] · [[Risk Scoring]] · [[Photon Outreach]] · [[Drone Dispatch]] · [[Drone Vision]] · [[Tabletop Model]] · [[Dashboard]]
- Reference: [[Data Sources]] · [[Tooling]] · [[Decisions]] · [[Demo Script]]
- Experiments: [[2026-11-07 Town cache build]] · [[2026-11-07 Demo run check]] · [[2026-11-08 July 2025 replay calibration]] · [[2026-11-08 Drone vision accuracy]] · [[2026-11-08 Tabletop synthetic accuracy]]

## Phase status

| Phase | Scope | Status |
|---|---|---|
| Phase 0 | Setup: ECC, CLAUDE.md, vault, `.env.example`, API contract | done (2026-11-07) |
| Phase 1 | Data layer: town cache, flood sim, road status, feeds, API | done: CHECKPOINT 1 backend verified 2026-11-07 |
| Map data access | [Collector and event-monitor handoff](../docs/MAP_DATA_ACCESS.md) | Texas-wide alerts, river readings, decoded rainfall/runoff grids, regional sensors, construction and optional crossing/camera context at `/texas`. TranStar live access pending. Normalization, grading and durable event storage are planned. |
| Phase 2 | Risk scoring + Stages 1-2 | done: CHECKPOINT 2 passed on a real phone |
| Phase 3 | Stage 3 escalation state machine | done: CHECKPOINT 3 passed on a real phone (reply closed the case) |
| Phase 4 | Photon integration | **Photon 2.0** texts + **voice calls** live (ElevenLabs over Photon SIP, call memory). The 2.0 inbound reply still needs a live test. Stable kept as fallback |
| Phase 5 | Drone + vision | done: CHECKPOINT 4 backend verified (real roof detection, boat required) |
| Phase 6 | Demo mode + polish, feature freeze 9 AM | backend done: 7-step run verified over WS ([[2026-11-07 Demo run check]]), talk track, claims sourced, pre-submission security review (1 HIGH fixed, TDD). Left: live `photon2` rehearsal, backup video, CHECKPOINT 5 with the frontend |
| Per-user danger | `feat/safety-core`: live feeds + profile risk + Photon/ElevenLabs stitched into one pipeline. A user's position goes to the hazard there, combined with their vulnerability and motion, giving a level (none/watch/warning/danger/critical) that drives the outreach ladder. Runs in replay and live. See [[Per-User Danger]] | done 2026-11-08: TDD core, API, live smoke test against real feeds, 2000-user July 2025 stress + fault injection ([[2026-11-08 Safety pipeline stress]]) |
| Live detection | Teammate's Texas collectors (`data_handoff.md`) feed Hill Country detection through `backend/observe/`: USGS gauges, NWS alerts (CAP lifecycle, polygons), MRMS radar rain at each crossing, NWS storm reports, NWPS forecasts. `REGION_MODE=live` or `POST /api/region/mode`. See [[Live Observations]] | done 2026-11-08. Replay is bit-for-bit unchanged (golden digest, 391 steps x 2 policies). The live path reproduces July 2025 belief exactly (0.00 in). Live smoke test passed against real feeds. |
| Hill Country | Real July 4, 2025 replay over Hunt → Ingram → Kerrville: HAND flood, chokepoints, priority, multi-drone tours, area risk (move low → high ground), Tello hookup. See [[Critical Point Drones]] | backend done 2026-11-08: 7-beat demo verified live over WS; python, fastapi and code reviewers done, all findings fixed |
| Drone vision | Water edge + elevation → water surface, depth at road with range, rise rate; YOLO + tracking for vehicles/people; alerts; spread; `POST /api/snapshots`. See [[Drone Vision]], [[2026-11-08 Drone vision accuracy]] | done 2026-11-08: 137 vision tests; Kerrville replay 16/16 inside range; 3 reviewers' HIGH findings fixed |
| Tabletop model | 3D-printed downtown Kerrville tray (1:5455, 3× vertical) with real dyed water. The drone camera measures the rise; the CAD heightmap is the ground truth. ArUco pose, bathtub truth, pour table. Fusion 360 MCP registered in `.mcp.json`. See [[Tabletop Model]] | built + synthetic-validated 2026-11-08: Park St within 0.2 m, bridge ranges honest; 23 TDD tests. Left: Fusion pass (add-in not running), print, real pour run |
| Driver profiles | Simulated State Farm profile (DSS, policy, claims, household, needs; `docs/driver-profile.md`) weights urgency in all 3 stages. See [[Risk Scoring]] | done 2026-11-08: colleague commit cherry-picked + baseline vulnerability score, TDD |
| Frontend | Driver app + ops console (`feat/frontend`), see [[Dashboard]], [[Design System]] | Built: driver app, ops console and `/present`, styled to State Farm's public design system. 86 unit tests plus a full 7-step Playwright demo. Verified on the live backend. |
| Ops console redesign | Weather and flood dashboard (NWS/Windy style): MRMS rain 1h/24h, modelled flood depth (10 m 3DEP), NWS-category gauges, closed/likely-flooded roads, colorbar, time slider over the July 4, 2025 replay | done 2026-11-07 on `feat/frontend`, merged into `feat/safety-core` 2026-11-08. Live data source stubbed in `src/wx/liveSource.ts` |

## Checkpoints

1. Data layer works: `/api/town` and `/api/state` respond, WS segment colors change as the clock advances.
2. Risk scoring + Stages 1-2: mock outreach log shows A's pre-trip text and B's turn-around and reroute events.
3. Stage 3 state machine: a stopped driver walks through every case state in order.
4. Drone + vision: drone flies to the stopped car and attaches a vision result.
5. Demo mode: the 7-step scripted run works end to end with both frontend views live on WS.

> [!warning] Checkpoint 4 and 5 depend on the frontend team
> Checkpoint 5 needs the driver view and ops dashboard on the same WS hub. Agree on [[Dashboard]] events in Phase 0.

## Next step

Backend is feature-complete for the demo. Next: CHECKPOINT 5 (frontend views live on the WS during `POST /api/demo/start`), then one full rehearsal in `PHOTON_MODE=photon2` on the teammates' phones (also tests the Photon 2.0 inbound reply live), then a backup video before the 9 AM freeze.

## Related

- [[Decisions]] for the dated log
- `vault/Experiments/` folder for runs and what broke
