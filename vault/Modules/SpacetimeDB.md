---
tags: [hitide, module, database]
status: done
updated: 2026-11-08
code: spacetime/floodwatch/, backend/db/
---

# SpacetimeDB (primary database)

**What:** one SpacetimeDB 2.14 database, `floodwatch`, published from a TypeScript module. It holds evidence, people, live per-user danger, outreach ladders and audit log, cases, drone snapshots and the inbound cursor. Static map, raster and model assets stay as files.

**Why** (HackUTD SpacetimeDB track):
- Reducers are atomic. Observation dedupe and revision chains are enforced in the database.
- Public tables can be subscribed to in real time: `danger_latest` is a live ops view.
- Private tables keep phones, positions and ladders owner-only.
- Ladders survive restarts, so there are no duplicate alerts.

**How:**
- The FastAPI backend calls reducers and reads with SQL over HTTP (`db/spacetime.py`). There is no Python SDK for 2.x.
- Runtime writes go through a write-behind queue, so the event loop never blocks.
- If SpacetimeDB is unreachable, the app falls back to SQLite and files and logs it loudly. `/api/health.database` shows which store is in use.

**Verified:** migration counts match and re-runs are idempotent; evidence bodies, chains and timestamps are identical to SQLite; end to end, Ruth's critical row, ladder and outreach are in SpacetimeDB; anonymous live subscriptions work; private tables are refused; a restart gives no duplicate poll.

Details: [docs/SPACETIMEDB.md](../../docs/SPACETIMEDB.md). Related: [[Per-User Danger]], [[Photon Outreach]], [[Live Observations]].
