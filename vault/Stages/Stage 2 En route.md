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
