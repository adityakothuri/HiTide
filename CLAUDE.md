# CLAUDE.md

HiTide: a HackUTD 2026 project built by a small team in about 24 hours. Submissions close Sun Nov 8, 12:00 PM CT.

## Mission

Protect opted-in State Farm drivers in flash floods in three stages: a pre-trip warning, an en-route "turn around" alert with reroute, and stopped-in-water escalation (calls, texts, family, responders, drone).
Town: Kerrville, TX on the Guadalupe River. The demo runs fully offline from the cached town data.
Full project brief and approved plan: `/Users/sandhyakothuri/.claude/plans/pasted-content-id-70ba-project-breezy-rivest.md` (outside the repo). Vault notes live in `vault/`.

## Priorities

1. A working demo beats perfect code. Ship the simplest thing that works, then improve it.
2. Make the UI look polished and intentional. Judges see the demo, not the code.
3. Keep secrets out of the repo. Use `.env` (gitignored) and add an `.env.example`.

## Working style

- Don't write tests unless asked. Do run the app or build to check changes actually work.
- Several people push to this repo, so keep changes focused and pull before starting big edits.
- Keep `README.md` up to date with the idea and the run commands as they settle.

## Stack

- Backend: Python 3.12 managed by `uv`, FastAPI + WebSockets, networkx, osmnx, py3dep, numpy, pydantic, pytest.
- Frontend: React + Vite + TypeScript (`frontend/`).
- Outreach: Photon Spectrum (Stable) for text and polls, ElevenLabs for voice. Mock mode until creds exist (`PHOTON_MODE=mock`).
- Data: OSM, USGS 3DEP, NWS, USGS Water Data, USGS Flood Impacts (see `vault/Data Sources.md`).

## Folder layout

- `backend/`: `api/` `sim/` `scoring/` `stages/` `outreach/` `drone/` `vision/` `feeds/` `demo/` `scripts/` `tests/` `config/`
- `frontend/`: React + Vite + TS driver view and ops dashboard
- `data/`: offline town cache, `drivers.json`, drone samples, `feeds_cache/`
- `vault/`: Obsidian notes (status, architecture, modules, decisions)
- `docs/`: API contract for the frontend team (`docs/api-contract.md`, published in Phase 0)

## Ownership

- `backend/` is owned by the Claude session on this machine.
- `frontend/` is owned by teammates.
- The contract between them is `docs/api-contract.md`. Change the contract there before changing a payload the frontend reads.

## Rules

- Update the Obsidian vault after every phase (`vault/00 Home.md` status table first).
- Core logic (risk scoring, road status, stop detection, escalation state machine, route checks) is TDD with pytest. This overrides "no tests unless asked" for those modules.
- Run backend: `cd backend && uv run uvicorn app.main:app --reload`
- Tests: `cd backend && uv run pytest`
- Never commit phone numbers or Photon creds. Use `.env` (copy from `.env.example`). Demo phones are allowlisted only through `DEMO_PHONE_*`.

## ECC usage

- Planner agent at the start of each phase (break it into tasks first).
- `tdd-workflow` skill for core logic: tests first, then implementation.
- Before a phase is marked done: `python-reviewer`, `fastapi-reviewer`, and `code-reviewer` agents.
- `security-scan` skill and `security-reviewer` agent before submission.
- Full asset list and which ones this project uses: `vault/Tooling.md`.
