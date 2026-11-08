---
tags: [floodwatch, stage, enroute]
status: todo
updated: 2026-11-07
---

# Stage 2: En route "turn around"

A moving driver is warned while still on the road, and gets a reroute if the way ahead is closed.

## Behavior

1. Look ahead along the remaining path within `stages.enroute_lookahead_m` (800 m in `backend/config/weights.yaml`).
2. If the path hits a closed segment, emit a `turn_around` event. The driver view plays it as TTS.
3. Emit a `reroute` event with a GeoJSON line for the new route.

> [!warning] No texts to moving drivers
> Enforced in the outreach layer by checking `driver.moving`. Unit-tested. Stage 2 never calls `send_text` for a moving driver.

## Movement

Drivers advance along their paths each tick (`sim/movement.py`), with a demo speed multiplier from the clock. Stage 2 reads the position from the same tick.

## Code

- `backend/stages/enroute.py` (planned)
- `backend/sim/movement.py` (planned)
- `backend/outreach/base.py` (planned): the `driver.moving` guard
- `backend/tests/test_route_check.py` (planned, TDD)

> [!note] Checkpoint 2
> The WS stream shows driver B's `turn_around` and `reroute` events.

## Related

- [[Stage 1 Pre-trip]] for drivers who have not left yet
- [[Stage 3 Stopped in water]] if the driver stops in water anyway
- [[Dashboard]] for the driver view

## Implementation (2026-11-07)

- Pure lookahead: `backend/stages/route_check.py` `lookahead`, tested in `backend/tests/test_route_check.py`.
- Motion: `backend/sim/movement.py` (immutable `DriverMotion`, `advance`, `ahead`, `position`).
- Wiring: `backend/stages/runner.py` `enroute_hook`. When a blocking edge is within `enroute_lookahead_m` (800 m), it emits `turn_around`, sends `tts_in_app` (the driver view speaks it), then reroutes from the end of the current edge and emits `reroute`.
- If there is no dry route, the car pulls over on dry ground.
- Guard: `backend/outreach/` blocks text, poll and voice to a physically moving driver (speed ≥ 0.5 m/s). Tested in `backend/tests/test_outreach_guard.py`.
- Demo result: demo-b got "Turn around" exactly 800 m before a 197 in crossing and was rerouted onto a 5.1 km dry route. A background driver was also rerouted.
