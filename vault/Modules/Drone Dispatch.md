---
tags: [hitide, module, drone]
status: todo
updated: 2026-11-07
---

# Drone Dispatch

> [!info] Multi-drone critical-point tours over the Hill Country replay live in [[Critical Point Drones]].

Sends a drone from a fixed station to a stopped driver. Path and arrival are simulated.

## Behavior

- Station: Kerrville Fire Station 1 (lat 30.0505, lon -99.1395), from `drone` in `backend/config/weights.yaml`.
- Straight-line flight at `drone.speed_mps` (25 m/s).
- Each tick emits `drone.update {lat, lon, eta_s}`.
- On arrival, attaches the vision result from [[Drone Vision]].
- Dispatch happens at T+3 min in [[Stage 3 Stopped in water]]. It does not block the responder handoff.

## Truck route check

From the nearest station, run a route check on a graph of edges with depth below 24 in (boat threshold). A path gives "Truck route available". No path gives "Boat required".

## Code

- `backend/drone/__init__.py` (exists, empty)
- `backend/drone/dispatch.py` (planned): path, ETA ticks, truck route check
- `backend/tests/test_route_check.py` (planned, TDD for the route check)
- `backend/config/weights.yaml` (exists): `drone` block

## Related

- [[Drone Vision]] for what the drone sees
- [[Stage 3 Stopped in water]]
