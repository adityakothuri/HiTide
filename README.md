# State Farm Flood Watch

Open `/texas` (or the home page) for the **Texas flood monitor**. It shows recent river stage, flood bulletins and road-related flood reports across the state. The observation window defaults to 30 minutes. Each source reports its own availability. The Kerrville test console is at `/console`.

> **Current team status:** read [State of the Union](docs/STATE_OF_THE_UNION.md)
> for the integrated evidence database, inspection workflow, setup, verification,
> limitations, and next milestones. The operations console is at `/console`.
> MongoDB is now the default evidence store; start a replica set before the backend
> (Windows: `powershell -NoProfile -File scripts/start-mongodb.ps1` after backend
> dependency setup), or explicitly select `FLOODWATCH_DB_BACKEND=sqlite`.
> The driver-rescue simulation described below remains a separate workflow.

HackUTD 2026: State Farm track ("The Worst Day, at Scale") + Photon track.

**Most flood deaths happen in vehicles.** Flood Watch protects opted-in State Farm drivers during flash floods in three stages:

1. **Before the trip:** drivers whose usual route crosses a flooded road get a text with a safer route. Teen drivers' parents get a copy.
2. **During the trip:** a spoken "Flooded road ahead. Turn around." alert and a reroute on dry roads. Moving drivers never get texts.
3. **Stopped in floodwater:** Flood Watch calls the driver, then their emergency contact, flags responders, and dispatches a drone whose vision reports the water level on the car and where people are.

Outreach order uses data State Farm already has (age, time of day, rising water, vehicle type). It never affects pricing.

Demo town: Kerrville, Texas, on the Guadalupe River. The roads come from OpenStreetMap and the elevation from USGS 3DEP (10 m), both cached offline.

Replay a historical NWS warning from `backend/` with `uv run python -m scripts.demo_flood_monitor`. The [map data access handoff](docs/MAP_DATA_ACCESS.md) covers raw collection, provider examples and the proposed normalization and MongoDB schema.

## Run it

```bash
# backend (Python 3.12 via uv)
cd backend && uv sync
uv run uvicorn app.main:app --reload          # http://localhost:8000/docs
uv run pytest -q                              # core logic tests

# start the scripted 90 s demo (watch it on the frontend, or the WS)
curl -X POST localhost:8000/api/demo/start
curl -X POST localhost:8000/api/demo/reset

# Photon (real iMessage texts/polls); needs creds in .env, see .env.example
cd photon-sidecar && npm install && npm start
```

Copy `.env.example` to `.env`. Without Photon creds everything runs in **mock mode**: outreach is logged and shown in the UI, but nothing is sent.

## Layout

| Path | What |
|---|---|
| `backend/` | FastAPI + WebSockets: flood sim, risk scoring, stages 1-3, outreach, drone, vision |
| `frontend/` | React + Vite: driver app view + ops dashboard (teammates) |
| `photon-sidecar/` | Node bridge to Photon Spectrum (`spectrum-ts`) |
| `data/` | Cached town, synthetic drivers, feed snapshots, drone images |
| `docs/api-contract.md` | Backend ⇄ frontend contract (REST + WS events) |
| `vault/` | Obsidian docs: problem, architecture, decisions, experiments, demo script |

Built with Claude Code + [Everything Claude Code](https://github.com/affaan-m/everything-claude-code). See `vault/Tooling.md`.
