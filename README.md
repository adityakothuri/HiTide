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

# start the scripted demo (~60 s, 7 steps; watch it on the frontend, or the WS)
curl -X POST localhost:8000/api/demo/start
curl -X POST localhost:8000/api/demo/reset

# Hill Country: drones to critical crossings, replaying the real July 4, 2025 flood (Hunt -> Ingram -> Kerrville)
curl -X POST 'localhost:8000/api/demo/start?scenario=hill_country&speed=150'   # ~2.5 min, 7 beats
curl localhost:8000/api/region/state | jq '.critical_points[0], .nodes[0].risk'
uv run python -m scripts.replay_report        # drones vs gauges-only vs naive patrol (two full replays)

# Hill Country LIVE: same detection on real-time Texas feeds (USGS gauges, NWS alerts, MRMS radar rain,
# NWS storm reports, NWPS river forecasts) for Hunt -> Kerrville, stepping every 30 s
REGION_MODE=live uv run uvicorn app.main:app   # or switch at runtime:
curl -X POST -H 'Origin: http://localhost:5173' 'localhost:8000/api/region/mode?mode=live'
curl localhost:8000/api/region/sources | jq   # each source: status, provenance, age of its newest data
# no MongoDB running? FLOODWATCH_DB_BACKEND=sqlite
RUN_SLOW=1 uv run pytest tests/test_replay_golden.py   # replay is bit-for-bit unchanged (~15 min)
# rebuild the region cache (needs network once): uv sync --extra data-build
#   uv run python -m scripts.build_region_cache && uv run python -m scripts.fetch_july2025 && uv run python -m scripts.build_region_nodes

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
| `mobile/` | Expo consumer app: Flood Watch (white/royal blue), mock data boundary for a future backend |
| `photon-sidecar/` | Node bridge to Photon Spectrum (`spectrum-ts`) |
| `data/` | Cached town, synthetic drivers, feed snapshots, drone images |
| `docs/api-contract.md` | Backend ⇄ frontend contract (REST + WS events) |
| `docs/drone-critical-points.md` | The drone critical-point math: chokepoints, priority, tours, area risk |
| `vault/` | Obsidian docs: problem, architecture, decisions, experiments, demo script |

Built with Claude Code + [Everything Claude Code](https://github.com/affaan-m/everything-claude-code). See `vault/Tooling.md`.
