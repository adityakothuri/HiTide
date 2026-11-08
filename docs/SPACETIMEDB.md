# SpacetimeDB: Flood Watch's primary database

Everything the backend persists now lives in one SpacetimeDB 2.14 database, `floodwatch`, published from a TypeScript module (`spacetime/floodwatch/spacetimedb/src/index.ts`). That covers:
- evidence and data-source health
- people (residents, drivers, enrolled users)
- live per-user danger
- outreach ladders and audit log
- escalation cases
- drone and vision snapshots
- inbound-reply cursors

The Python FastAPI backend writes through reducers and reads through SQL. Dashboards can **subscribe** to the public tables (`danger_latest`, `app_user`, `source`, `ingestion_run`) and get live row updates with no polling.

## Why SpacetimeDB here

- **One transactional store for a safety system.**
  - Each write is one reducer, which runs as an atomic transaction.
  - Observation dedupe and revision chains are enforced inside the database (`add_observation`), not by hoping two processes don't race.
- **Real time for free.** The ops view (`danger_latest`) is just a table. Any client subscribed to `SELECT * FROM danger_latest WHERE level = 'critical'` sees people change level as the flood moves.
- **Privacy by table, not by code path.**
  - Everything that can identify or locate a real person is in a **private** table: phone numbers, profiles, positions, outreach ladders and message bodies, cases, drone snapshots, community reports. Only the database owner, which is the backend, can read them.
  - Every write reducer rejects any caller that isn't the owner identity recorded at first publish.
- **Restarts don't re-alert anyone.** Outreach ladders (`response_state`) used to live only in memory. A restart in live mode now picks up exactly where it left off.

## Tables

| Table | Visibility | What | Was |
|---|---|---|---|
| `source`, `ingestion_run` | public | Data sources and their fetch health | SQLite / MongoDB |
| `app_user` | public | People, projected: enrolled users show first name only, no age, no tags, home rounded to about 1 km | `region_users.json`, `drivers.json`, `user_registry.json` |
| `danger_latest` | public | Current level, top reason, advice, confidence. Position only for simulated users, or real users at DANGER or above, rounded to about 1 km | (new) |
| `observation`, `raw_record`, `setting`, `inspection_task` | private | Evidence, provider payloads, the town dataset, inspection tasks. Community reports can name people | SQLite / MongoDB |
| `user_contact`, `user_profile` | **private** | Phones, emergency contacts, profiles | the people files |
| `user_track` | private | Last position and planned route | `safety_state.json` |
| `response_state` | private | Each person's outreach ladder | memory only (**new: survives restarts**) |
| `outreach_event` | private | Every text, poll, call and status. Bodies name people and roads; never phone numbers | `outreach_log.jsonl` |
| `escalation_case` | private | Stopped-in-water cases and timelines (position and contacts) | memory only |
| `vision_snapshot` | private | Drone and vision evidence (can include people in water) | memory only |
| `kv`, `config` | private | Photon 2.0 inbound cursor; owner identity | memory only |

Anything private is read by the backend (owner token) and served through its API, which keeps its own privacy rules. Clients can subscribe only to the four public tables.

**Not in the database:** large static assets stay as files.
- Road graphs, DEMs, weather tiles, models, drone images.
- `feeds_cache/`, the offline fixtures.

## Run it

```bash
curl -sSf https://install.spacetimedb.com | sh     # once: SpacetimeDB CLI 2.14
scripts/spacetime_up.sh --migrate                  # start local server, publish, copy existing data in (idempotent)
./dev.sh                                           # or: cd backend && uv run uvicorn app.main:app
curl localhost:8000/api/health | jq .database      # {"backend": "spacetime", ...}
spacetime sql floodwatch "SELECT * FROM danger_latest WHERE level = 'critical'"
spacetime subscribe floodwatch "SELECT * FROM danger_latest WHERE level = 'critical'" --anonymous
```

**Settings:**
- `FLOODWATCH_DB_BACKEND`: `spacetime` (the default in both `DATA_MODE`s), `sqlite`, `mongodb` or `memory`.
- `SPACETIME_URL`: default `http://127.0.0.1:3000`.
- `SPACETIME_DB`: default `floodwatch`.
- `SPACETIME_TOKEN`: defaults to your `spacetime` CLI login. Use `spacetime login show --token` to put it in `.env`.
- `SPACETIME_SERVER=maincloud`: publish and connect to SpacetimeDB Maincloud after `spacetime login`.

**If SpacetimeDB isn't running**, the backend logs `FALLING BACK TO SQLITE` and keeps working on the old SQLite and file stores. `/api/health.modes.db` then reads `sqlite (fallback: SpacetimeDB unreachable at …)`.

## How it works

- `backend/db/spacetime.py`: a small httpx client.
  - Reducer calls send positional JSON arguments.
  - SQL rows are decoded with their schema: options come back as `[0, v]` or `[1, []]`, and timestamps as micros.
  - All SQL string values go through one `quote()` helper.
- `backend/db/evidence.py`: the evidence store.
  - It has the same interface as the SQLite and Mongo stores, so `EvidenceService` and its routes are unchanged.
  - Validation and semantic hashing are shared with SQLite.
  - The geo queries use bounding-box columns plus exact shapely geometry. These were Mongo-only before.
- `backend/db/store.py`: the user, safety, outreach, case, snapshot and key-value data store. It has Spacetime, file-fallback and in-memory implementations.
  - **Write-behind:** runtime writes go through one background queue, so the event loop and simulation steps never wait on the database.
  - **Failures are counted:** a failed write is counted in `/api/health.database.writes`, not swallowed.
  - **Outages fail fast:** if the database becomes unreachable mid-run, remote writes pause for 15 s. Outreach events go to the JSONL log instead, and the migration re-imports them. Ladder and position rows are re-sent on the next refresh.
- `backend/safety/persist.py`: writes only changed rows (dangers, ladders, positions), and restores live-mode state on restart.
- `backend/scripts/migrate_to_spacetime.py`: moves the SQLite DB (or Mongo with `--mongo-uri`), the JSON people files, the position file and the JSONL outreach log in. `--verify` prints source and SpacetimeDB counts side by side.

## Verified (2026-11-08)

| Check | Result |
|---|---|
| Migration (`--verify`) | 341 observations, 341 raw records, 16 ingestion runs, the 1.4 MB town dataset, 351 people (251 residents + 100 Kerrville drivers), 6,038 outreach events. All counts match, and a second run changes nothing (idempotent). |
| Evidence parity | All 341 observation bodies, revision chains and original timestamps are **identical** between SQLite and SpacetimeDB. |
| End to end | Backend on SpacetimeDB, July 4 replay at 600×, Ruth pings. `danger_latest` shows her at `critical` with the same reason as the API, her outreach ladder is in `response_state`, and her calls, poll and family contact are in `outreach_event`. 0 failed writes. |
| Real-time | An anonymous `spacetime subscribe` to `danger_latest` streams live row updates during the replay. |
| Privacy | Anonymous SQL or subscription to every private table fails (11 tables are checked in `test_db_contract.py`). Anonymous reducer calls are rejected by the owner check. The local server binds to 127.0.0.1 only. |
| Restart | A new monitor on the same database restores the ladder and position, and sends **no** second poll (`tests/test_safety_persist.py`). |
| Tests | `tests/test_db_contract.py` runs one contract against the memory, file and real SpacetimeDB stores. The SpacetimeDB run uses a throwaway published database that is deleted afterwards. Plus client, factory and fallback tests. |
