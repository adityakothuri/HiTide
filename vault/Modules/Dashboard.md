---
tags: [floodwatch, module, frontend]
status: todo
updated: 2026-11-07
---

# Dashboard

> [!note] Owned by the frontend team
> Teammates build the driver view and the ops dashboard in `frontend/`. Backend contract: `docs/api-contract.md`. This note only records what the backend sends.

## Two views

- **Driver view**: pre-trip and turn-around alerts with TTS, reroute line on the map, "I'm safe" and "I need help" buttons (`POST /api/cases/{id}/reply`).
- **Ops dashboard**: map of segment status, driver positions, case cards with `reasons[]`, outreach log, drone position, counters.

## Backend endpoints

Live now (per the status line in `docs/api-contract.md`):

- `GET /api/town`: segments as GeoJSON
- `GET /api/state`: snapshot
- `GET /api/feeds`: feed status with `source: live|cached|unavailable`
- `POST /api/demo/start` and `POST /api/demo/reset`
- `WS /ws`: `snapshot`, `alert`, `segments.update`

Planned for Phases 2-5, same shapes as in the contract:

- WS events `drivers.update`, `outreach`, `case.update`, `drone.update`, `counters`
- `GET /api/cases`, `POST /api/cases/{id}/reply`, `GET /api/drivers/{id}`
- `GET /api/mock/stream`: replays a recorded demo sequence so the frontend can build before the sim is ready

## Code

- `frontend/` (not created yet, teammates)
- `backend/api/ws.py` (exists): WS hub
- `backend/api/routes.py` (exists): REST routes
- `backend/api/schemas.py` (exists): Pydantic models for the events
- `backend/app/main.py` (exists): app, CORS (open for the Vite dev server), routers
- `backend/api/routes_cases.py` (planned): reply endpoint and case list
- `docs/api-contract.md` (exists): the contract

## Related

- [[Architecture]] for the WS hub position
- [[Stage 2 En route]] for the driver view alerts
- [[Stage 3 Stopped in water]] for the case cards
