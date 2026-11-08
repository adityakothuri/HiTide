# CLAUDE.md

HiTide: a HackUTD 2026 project built by a small team in about 24 hours. Submissions close Sun Nov 8, 12:00 PM CT.

## Mission

Protect opted-in State Farm drivers in flash floods in three stages: a pre-trip warning, an en-route "turn around" alert with reroute, and stopped-in-water escalation (calls, texts, family, responders, drone).
Town: Kerrville, TX on the Guadalupe River. The demo runs fully offline from the cached town data.
Status and notes live in `vault/` (start at `vault/00 Home.md`). Presentation material is in `presentation/`.

## Priorities

1. A working demo beats perfect code. Ship the simplest thing that works, then improve it.
2. Make the UI look polished and intentional. Judges see the demo, not the code.
3. Keep secrets out of the repo. Use `.env` (gitignored) and add an `.env.example`.

## Working style

- Don't write tests unless asked. Do run the app or build to check changes actually work.
- Everyone works on `main`. Several people push to it, so keep changes focused, `git pull` before starting, and run the tests before pushing.
- Keep `README.md` up to date with the idea and the run commands as they settle.

## Stack

- Backend: Python 3.12 managed by `uv`, FastAPI + WebSockets, networkx, osmnx, py3dep, numpy, pydantic, pytest.
- Frontend: React + Vite + TypeScript (`frontend/`).
- Database: SpacetimeDB (primary, `spacetime/`, `scripts/spacetime_up.sh`); the backend falls back to SQLite if it isn't running. MongoDB is optional.
- Outreach: Photon 2.0 (`PHOTON_MODE=photon2`, Spectrum "stable" sidecar as fallback) for texts and polls, ElevenLabs for voice. Mock mode until creds exist (`PHOTON_MODE=mock`).
- Mobile: Expo / React Native consumer app (`mobile/`).
- Drone: DJI Tello bridge (`backend/scripts/tello_dashboard.py`) and vision (`backend/vision/`, `backend/gauge/`).
- Data: OSM, USGS 3DEP, NWS, USGS Water Data, USGS Flood Impacts (see `vault/Data Sources.md`).

## Folder layout

- `backend/`: `api/` `app/` `db/` `evidence/` `feeds/` `observe/` `fusion/` `sim/` `critical/` `scoring/` `safety/` `stages/` `routing/` `population/` `outreach/` `drone/` `vision/` `gauge/` `demo/` `scripts/` `tests/` `config/`
- `frontend/`: React + Vite + TS: Texas monitor, ops console, driver view, `/present`
- `mobile/`: Expo consumer app
- `spacetime/`: SpacetimeDB TypeScript module
- `photon-sidecar/`: Node bridge to Photon Spectrum
- `data/`: offline town and region cache, `drivers.json`, drone samples, `feeds_cache/`, gauge tray CAD
- `vault/`: Obsidian notes (status, architecture, modules, decisions, experiments)
- `docs/`: API contract (`docs/api-contract.md`) and technical docs; `docs/history/` holds superseded records
- `presentation/`: charts, screenshots, mockups and demo videos for the pitch

## Ownership

- Backend and frontend are both shared; coordinate in the team chat before large refactors.
- The contract between them is `docs/api-contract.md`. Change the contract there before changing a payload the frontend reads.

## Rules

- Update the Obsidian vault after every phase (`vault/00 Home.md` status table first).
- Core logic (risk scoring, road status, stop detection, escalation state machine, route checks) is TDD with pytest. This overrides "no tests unless asked" for those modules.
- Run everything: `./dev.sh` (test data, offline) or `./dev.sh real` (live feeds; add `--live-outreach` for real texts). Backend only: `cd backend && uv run uvicorn app.main:app --reload` (defaults to `DATA_MODE=test`)
- Tests: `cd backend && uv run pytest`
- Never commit phone numbers or Photon creds. Use `.env` (copy from `.env.example`). Demo phones are allowlisted only through `DEMO_PHONE_*`.

## ECC usage

- Planner agent at the start of each phase (break it into tasks first).
- `tdd-workflow` skill for core logic: tests first, then implementation.
- Before a phase is marked done: `python-reviewer`, `fastapi-reviewer`, and `code-reviewer` agents.
- `security-scan` skill and `security-reviewer` agent before submission.
- Full asset list and which ones this project uses: `vault/Tooling.md`.
