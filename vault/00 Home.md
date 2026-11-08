---
tags: [floodwatch, home, status]
status: in-progress
updated: 2026-11-07
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
- Modules: [[Flood Simulation]] · [[Risk Scoring]] · [[Photon Outreach]] · [[Drone Dispatch]] · [[Drone Vision]] · [[Dashboard]]
- Reference: [[Data Sources]] · [[Tooling]] · [[Decisions]] · [[Demo Script]]
- Experiments: [[2026-11-07 Town cache build]]

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
| Live Tello + gauge tray | Real drone in the console, water depth from the printed gauge tray ([plan](../docs/gauge-water-level-plan.md), [setup](../docs/gauge-tray-setup.md)) | done on `feat/gauge-water-level` (2026-11-08): synthetic sweep 100% within 0.5 ft mid-step (stand mode), console verified end to end in the browser; awaiting the physical print |
| Phase 6 | Demo mode + polish, feature freeze 9 AM | todo |
| Frontend | Driver app + ops console (`feat/frontend`), see [[Dashboard]], [[Design System]] | Checkpoint 2: tokens, primitives, data layer (73 tests) |

## Checkpoints

1. Data layer works: `/api/town` and `/api/state` respond, WS segment colors change as the clock advances.
2. Risk scoring + Stages 1-2: mock outreach log shows A's pre-trip text and B's turn-around and reroute events.
3. Stage 3 state machine: a stopped driver walks through every case state in order.
4. Drone + vision: drone flies to the stopped car and attaches a vision result.
5. Demo mode: the 7-step scripted run works end to end with both frontend views live on WS.

> [!warning] Checkpoint 4 and 5 depend on the frontend team
> Checkpoint 5 needs the driver view and ops dashboard on the same WS hub. Agree on [[Dashboard]] events in Phase 0.

## Next step

Next: Phase 2/3 per the planner breakdown. Shared world state and routing, movement, outreach guard (TDD), pre-trip route check (TDD), en-route lookahead, stop detection and escalation (TDD), then the demo scenario. Frontend team: see `docs/api-contract.md`. The live data is ready.

The tag-free drone gauge now reads straight-on stand views in simulation. Physical-print verification is pending. See section 9 of [the drone gauge handoff](../docs/AGENT_HANDOFF_drone_gauge.md).

## Related

- [[Decisions]] for the dated log
- `vault/Experiments/` folder for runs and what broke

Demo overlay tracking startup fixed and verified through the browser Anchor button with moving frames. See the drone gauge handoff.
Live drone overlay now combines per-frame blue-dye regions with gauge-measured depth, CAD car projection and tray outline. Automatic gauge start and periodic pose refresh added. Local dashboard security audit fixes applied. See the drone gauge handoff.
Console and drone dashboard now share frame-synchronous annotations, user-aligned vehicle/tray tracking,
visibility controls and explicitly labelled manual demo depth. See drone gauge handoff for timings and validation.
Dedicated Drone tab is live at /drone, with just the drone workflow and shared controls.
Demo depth standard deviation is configurable in the Drone tab and dashboard. The large Drone heading was removed.
Gauge presentation update verified with browser screenshots. Manual depth now feeds the Water gauge card,
with default empty state on blank video. Valid gauge poses automatically seed tracked car/tray boxes.
Live restart was blocked by automatic approval and remains pending.
