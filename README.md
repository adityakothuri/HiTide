# State Farm Flood Watch

HackUTD 2026: State Farm track ("The Worst Day, at Scale") + Photon track.

**Most flood deaths happen in vehicles.** Flood Watch protects opted-in State Farm drivers during flash floods in three stages:

1. **Before the trip:** drivers whose usual route crosses a flooded road get a text with a safer route. Teen drivers' parents get a copy.
2. **During the trip:** a spoken "Flooded road ahead. Turn around." alert and a reroute on dry roads. Moving drivers never get texts.
3. **Stopped in floodwater:** Flood Watch calls the driver, then their emergency contact, flags responders, and dispatches a drone whose vision reports the water level on the car and where people are.

Outreach order uses data State Farm already has (age, time of day, rising water, vehicle type). It never affects pricing.

Demo town: Kerrville, Texas, on the Guadalupe River. The roads come from OpenStreetMap and the elevation from USGS 3DEP (10 m), both cached offline.

## Run it

```bash
# backend (Python 3.12 via uv)
cd backend && uv sync
uv run uvicorn app.main:app --reload          # http://localhost:8000/docs
uv run pytest -q                              # core logic tests

# start the scripted demo (~60 s, 7 steps; watch it on the frontend, or the WS)
curl -X POST localhost:8000/api/demo/start
curl -X POST localhost:8000/api/demo/reset

# frontend (driver view + ops dashboard)
cd frontend && npm install && npm run dev
```

Copy `.env.example` to `.env`. `PHOTON_MODE` picks how outreach is sent:

| `PHOTON_MODE` | Texts | Calls |
|---|---|---|
| `mock` (default) | logged + shown in the UI, nothing sent | logged, nothing placed |
| `photon2` | Photon 2.0 shared iMessage line, replies over its WebSocket | ElevenLabs agent over Photon SIP |
| `stable` | Photon Spectrum via `photon-sidecar/` (`npm install && npm start`) | |

Only allowlisted demo numbers (`DEMO_PHONE_A/B/C`) are ever contacted. Every other driver is mock-only. Setup scripts: `uv run python -m scripts.photon2_enroll --write-env` and `uv run python -m scripts.elevenlabs_setup`.

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
