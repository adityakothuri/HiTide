---
tags: [floodwatch, home, status]
status: in-progress
updated: 2026-11-07
---

# State Farm Flood Watch

Protect opted-in State Farm drivers in flash floods. Kerrville, TX on the Guadalupe River. Submissions close **Sun Nov 8, 12:00 PM CT**.

> [!note] How to read this vault
> Start with [[Problem]] and [[Architecture]]. Stage notes describe behavior. Module notes link to the code that implements each piece. Decisions and experiments record why things are the way they are.

## Map of content

- Why: [[Problem]] · [[Pitch]] · [[Privacy and Consent]]
- How it works: [[Architecture]] · [[Stage 1 Pre-trip]] · [[Stage 2 En route]] · [[Stage 3 Stopped in water]]
- Modules: [[Flood Simulation]] · [[Risk Scoring]] · [[Photon Outreach]] · [[Drone Dispatch]] · [[Drone Vision]] · [[Dashboard]]
- Reference: [[Data Sources]] · [[Tooling]] · [[Decisions]] · [[Demo Script]]
- Experiments: [[2026-11-07 Town cache build]]

## Phase status

| Phase | Scope | Status |
|---|---|---|
| Phase 0 | Setup: ECC, CLAUDE.md, vault, `.env.example`, API contract | done (2026-11-07) |
| Phase 1 | Data layer: town cache, flood sim, road status, feeds, API | done: CHECKPOINT 1 backend verified 2026-11-07 |
| Phase 2 | Risk scoring + Stages 1-2 | in progress: risk scoring done (TDD) |
| Phase 3 | Stage 3 escalation state machine | todo |
| Phase 4 | Photon integration (spike, timeboxed) | todo |
| Phase 5 | Drone + vision | todo |
| Phase 6 | Demo mode + polish, feature freeze 9 AM | todo |

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

## Related

- [[Decisions]] for the dated log
- `vault/Experiments/` folder for runs and what broke
