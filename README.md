# State Farm Flood Watch

Open `/texas` (or the home page) for the **Texas flood monitor**. It shows recent river stage, flood bulletins and road-related flood reports across the state. The observation window defaults to 30 minutes. Each source reports its own availability. The Kerrville test console is at `/console`.

The monitor also includes decoded NOAA rainfall/runoff previews, NWPS river summaries, LCRA and Harris County measurements, and construction restrictions. Expand Source availability for access failures and timestamp exclusions. Camera locations and timestamp-unverified crossing status require the source-context checkbox. Detailed source mappings and remaining integration limits are in [the data handoff](docs/MAP_DATA_ACCESS.md).

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

# frontend (Node 22+)
cd frontend && npm install && npm run dev       # http://localhost:5173

# consumer mobile app (Expo SDK 58, iOS/Android, local demo data); see mobile/README.md
cd mobile && npm install && npx expo start      # press i for the iOS simulator
```

Frontend views (add `?mode=live` or `?mode=mock` to force a data source; the default tries the backend and falls back to the recorded offline demo after 2.5 s):

| URL | What it is |
|---|---|
| `/present` | Demo view: the driver's phone next to the ops console, one shared data stream |
| `/driver` | Driver app (390×844). `?driver=demo-a\|demo-b\|demo-d` pins a persona |
| `/console` | State Farm flood operations console (1440×900) |
| `/gallery` | Component gallery in every state |

Maps use CARTO's keyless vector basemaps (OpenStreetMap data), so they need internet. If the tiles can't load within 4 s, the map falls back to the bundled Kerrville road data automatically and the demo keeps running.

Press **Shift+D** for presenter controls (run, next step, reset, which persona the phone shows). Before presenting, tap "Test spoken alert" in the phone's settings once: browsers block speech until the page has had a click.

Copy `.env.example` to `.env`. Without Photon creds everything runs in **mock mode**: outreach is logged and shown in the UI, but nothing is sent.

## Layout

| Path | What |
|---|---|
| `backend/` | FastAPI + WebSockets: flood sim, risk scoring, stages 1-3, outreach, drone, vision |
| `frontend/` | React + Vite: driver app view + ops dashboard (teammates) |
| `mobile/` | Expo consumer app: Flood Watch (white/royal blue), mock data boundary for a future backend |
| `photon-sidecar/` | Node bridge to Photon Spectrum (`spectrum-ts`) |
| `data/` | Cached town, synthetic drivers, feed snapshots, drone images |
| `docs/api-contract.md` | Backend ⇄ frontend contract (REST + WS events) |
| `vault/` | Obsidian docs: problem, architecture, decisions, experiments, demo script |

Built with Claude Code + [Everything Claude Code](https://github.com/affaan-m/everything-claude-code). See `vault/Tooling.md`.
