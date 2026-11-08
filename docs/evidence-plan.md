# Evidence-to-drone milestone

## Goal
Aggregate timestamped flood evidence, expose uncertainty at consequential crossings,
rank inspections, and ingest a simulated inspection that changes connectivity and priorities.
Kerrville is the first bounded area. Driver telemetry remains separate future work.

## Parallel task ownership
1. Data foundation: `backend/evidence/models.py`, `store.py`, `ingestion.py` and their tests.
2. Analysis and API: `backend/evidence/analysis.py`, `service.py`, `routes.py`, `demo.py` and their tests.
3. Operations UI: `frontend/src/evidence/`, `App.tsx`, browser checks.
4. Integration: environment, lifespan, background polling, regression checks, documentation.

## Acceptance criteria
- Preserve provenance, observation time and retrieval time; repeated polls do not manufacture fresh observations.
- Persist observation history and inspection state across restart; integrity diagnostics are non-destructive.
- Missing evidence is unknown; gauge height is never silently converted into road depth.
- A stale remaining exit outranks a stale road whose inspection cannot change connectivity.
- A completed inspection inserts evidence and updates connectivity/priority; inconclusive evidence stays uncertain.
- Simulated data and limited coverage are visible; upstream failure keeps old evidence with its original age.
- Desktop setup, existing backend tests, frontend tests/build, and the browser workflow are checked.

## Database decision
No database files, SQL schemas, migrations, or connection configuration existed in this checkout.
The legacy system uses in-memory state and JSON caches. Those caches are not an old SQL database.
SQLite is the first local persistent backend because it runs without Docker or a database service.
Spatial reasoning uses the existing directed graph and geometry tools. PostGIS remains a later
deployment option, not a dependency claimed to be running locally.

## Repository harness
The user authorized implementation of the earlier plan and parallel work. Agents read the checked-in
ECC planner/reviewer/TDD definitions. The native Codex runtime executes parallel work with explicit
file ownership. The deterministic ECC harness audit runs in the terminal.
The separate Claude CLI is installed but was not authenticated at intake, so no Claude-hosted
agent runs are claimed. `scripts/review-harness.ps1` runs the repository's actual Claude reviewer
definitions concurrently once the user signs in; VS Code tasks expose it and the app servers.
No commits or publishing are part of this milestone.

## Verification record
At intake: frontend 75 tests passed and production build passed. Backend tests could not run until
Python 3.12 and uv were installed. After environment setup, legacy tests passed; the database agent's
three failing regression tests reproduced missing integrity/transaction helpers and poll metadata
deduplication, then passed after fixes. Initial database implementation predates harness steering;
do not interpret that targeted RED/GREEN evidence as proof the whole module was test-first.

Final integration results and limitations are recorded in `vault/Experiments/2026-11-07 Evidence milestone.md`.
