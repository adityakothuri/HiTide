---
tags: [hitide, stage, pretrip]
status: todo
updated: 2026-11-07
---

# Stage 1: Pre-trip warning

Before a driver leaves, warn them if their usual route crosses closed or at-risk water.

## Trigger

A warning is active (NWS alert or simulated river rise). For each **non-moving** driver:

1. Intersect the driver's usual route edges (2-3 per driver) with segments that are `closed` or worse, or at-risk.
2. If any match, compute an alternate route with `networkx.shortest_path` on the graph with flooded edges removed.
3. Send a text through [[Photon Outreach]] (`outreach.send_text`). For teen drivers (16-19), send a copy to the parent.
4. Dedupe per driver per warning, so the same warning never sends twice.

## Output

- `outreach` event on `/ws` with the message and mode (`mock` or `photon`)
- `alert` event with the alternate route when one exists
- Case card reasons from [[Risk Scoring]]

## Code

- `backend/stages/pretrip.py` (planned)
- `backend/scoring/road_status.py` (exists): status per segment
- `backend/sim/drivers.py` (exists): usual routes per driver
- `backend/tests/test_route_check.py` (planned, TDD)

> [!note] Checkpoint 2
> In mock mode, the outreach log shows driver A's pre-trip text. Once Photon creds exist, A's real phone gets it.

## Related

- [[Stage 2 En route]] for drivers already moving
- [[Architecture]] for the full pipeline

## Implementation (2026-11-07)

- Pure check: `backend/stages/route_check.py` (`route_hits`, `plan_pretrip`), tested in `backend/tests/test_route_check.py` (TDD).
- Wiring: `backend/stages/runner.py` `pretrip_hook`. It runs every tick while an alert is active. Dedupe key is `(driver, alert)`. Drivers on a trip are skipped.
- Safer route: `backend/sim/routing.py` `dry_route` (networkx `restricted_view` with closed edges removed in both directions).
- If there is no dry route, the text says "delay your trip".
- Teen: a parent copy is sent with `recipient=parent`.
- Demo result: demo-a and demo-t (whose parent is A) were warned 3.6 s into the run, with a 4.5 km safer route. 34 drivers were warned overall.
