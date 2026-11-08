# State Farm Flood Watch

Open `/texas` (or the home page) for the **Texas flood monitor**. It shows recent river stage, flood bulletins and road-related flood reports across the state. The observation window defaults to 30 minutes. Each source reports its own availability. The Kerrville test console is at `/console`.

The monitor also includes decoded NOAA rainfall/runoff previews, NWPS river summaries, LCRA and Harris County measurements, and construction restrictions. Expand Source availability for access failures and timestamp exclusions. Camera locations and timestamp-unverified crossing status require the source-context checkbox. Detailed source mappings and remaining integration limits are in [the data handoff](docs/MAP_DATA_ACCESS.md).

> **Test evidence for the presentation:** [docs/TEST_EVIDENCE.md](docs/TEST_EVIDENCE.md) (811 tests pass; July 2025 replay; 2,000-user stress test).
>
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

# PER-USER DANGER (backend/safety/): where is each opted-in resident, what is the water doing there, how vulnerable
# are they -> none/watch/warning/danger/critical -> text / poll / call / family / responders. Runs in replay AND live.
uv run python scripts/gen_region_users.py                      # 250 simulated Kerr County residents (committed)
curl localhost:8000/api/safety/summary | jq                    # level counts, degraded sources
curl -X POST localhost:8000/api/users/hc-ruth/location -H 'content-type: application/json' \
     -d '{"lat": 30.0688, "lon": -99.3345}' | jq '.level, .reasons, .response'
curl 'localhost:8000/api/users/at-risk?min_level=danger' | jq '.users[] | {user_id, level, reasons: .reasons[0]}'
uv run python scripts/stress_safety.py --users 2000 --fault none   # accuracy vs replay truth + spam + latency
uv run python scripts/stress_safety.py --load 20000                # latency only
# env: OUTREACH_ALLOW_ENROLLED=1 lets consented API-enrolled +E.164 users get real sends (default off);
#      SAFETY_DEMO=1 shrinks ladder timers 10x; SAFETY_REGISTRY_PATH / SAFETY_STATE_PATH move the gitignored runtime files

# ops console weather layers (data/wx/, served offline by the frontend after `npm run sync-wx`; needs network once)
uv run python -m scripts.fetch_mrms_tiles     # archived MRMS rain tiles, Kerr County, Jul 4 2025, recolored to an NWS-style ramp
uv run python -m scripts.build_wx_flood       # 10 m 3DEP DEM -> flood-depth PNG per river rise + road closure thresholds
uv run python -m scripts.build_wx_gauges      # 5 USGS gauges + NWS flood categories + replay warning timeline

# drone vision: water edge + elevation -> depth over the road; vehicles/people in water -> alerts
uv sync --extra vision && uv run python scripts/fetch_vision_models.py    # once, needs network (SegFormer, CLIPSeg, YOLO)
uv run python -m vision.run_pipeline --source synth:cp-0014 --at 2025-07-04T10:45:00Z --post   # replay truth hover
uv run python -m vision.run_pipeline --source images:../data/drone_samples --post               # real flood photos
uv run pytest tests/test_vision_*.py -q                                    # accuracy: vault/Experiments/2026-11-08 Drone vision accuracy.md

# tabletop model: 3D-printed downtown Kerrville tray (1:5455, 3x vertical) + CAD ground truth for the drone camera
uv run python -m scripts.build_print_model                                 # STLs, truth.npz, pour table, ArUco sheet -> data/print_model/
uv run python -m scripts.run_tabletop --source synth --rise 3,6,9,12,13    # pre-print accuracy vs truth
uv run python -m scripts.run_tabletop --source images:<dir> --level-mm 11.1 # real pour: phone/Tello frames, caliper truth
uv run python -m scripts.check_print_export <fusion_export.stl>           # Fusion (MCP in .mcp.json) kept the terrain
# runbook: vault/Modules/Tabletop Model.md

# frontend (driver view + ops dashboard)
cd frontend && npm install && npm run dev
```

Copy `.env.example` to `.env`. `PHOTON_MODE` picks how outreach is sent:

| `PHOTON_MODE` | Texts | Calls |
|---|---|---|
| `mock` (default) | logged + shown in the UI, nothing sent | logged, nothing placed |
| `photon2` | Photon 2.0 shared iMessage line, replies over its WebSocket | ElevenLabs agent over Photon SIP |
| `stable` | Photon Spectrum via `photon-sidecar/` (`npm install && npm start`) | |

Only allowlisted demo numbers (`DEMO_PHONE_A/B/C`) are ever contacted, plus API-enrolled consented users when `OUTREACH_ALLOW_ENROLLED=1`. In a live mode every other send is logged as `suppressed` (never a fake "sent"). Setup scripts: `uv run python -m scripts.photon2_enroll --write-env` and `uv run python -m scripts.elevenlabs_setup`.

## Layout

| Path | What |
|---|---|
| `backend/` | FastAPI + WebSockets: flood sim, risk scoring, stages 1-3, outreach, drone, vision |
| `frontend/` | React + Vite: driver app view + ops dashboard (teammates) |
| `photon-sidecar/` | Node bridge to Photon Spectrum (`spectrum-ts`) |
| `data/` | Cached town, synthetic drivers, feed snapshots, drone images |
| `docs/api-contract.md` | Backend ⇄ frontend contract (REST + WS events) |
| `docs/drone-critical-points.md` | The drone critical-point math: chokepoints, priority, tours, area risk |
| `vault/` | Obsidian docs: problem, architecture, decisions, experiments, demo script |

Built with Claude Code + [Everything Claude Code](https://github.com/affaan-m/everything-claude-code). See `vault/Tooling.md`.
