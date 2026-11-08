---
tags: [floodwatch, stage, escalation]
status: todo
updated: 2026-11-07
---

# Stage 3: Stopped in water

A driver stops on a flooded segment. We call them, contact family, dispatch a drone, and hand the case to responders.

## Stop detection

A driver is "stopped in water" when all of these hold:

- speed is about 0 for at least `stages.stop_seconds` (60 s)
- not within `stages.dest_radius_m` (75 m) of a known destination
- on a segment with depth above `caution` (3 in)

Stop detection is TDD (`backend/tests/test_stop_detect.py`, planned).

## Case states

`Monitoring → Calling → ContactingFamily → DroneEnRoute → Verified → HandedToResponders → Resolved`

| State | Meaning |
|---|---|
| Monitoring | Stopped detected, case open, no contact yet |
| Calling | Voice call and text to the driver (T+0) |
| ContactingFamily | No reply: text the emergency contact (T+2 min) |
| DroneEnRoute | Drone dispatched to the location (T+3 min) |
| Verified | Drone vision confirmed people and car position |
| HandedToResponders | Responder packet sent (location, people count, depth) |
| Resolved | Driver replied safe, or responders closed the case |

Any reply moves the case to `Resolved` or downgrades it.

## Timeline

| Time | Action | Demo profile |
|---|---|---|
| T+0 | Call the driver (voice or text) | 0 s |
| T+2 min | Contact family | 12 s |
| T+3 to 5 min | Dispatch the drone; the window runs T+3 to T+5 | 18 s |

Timers come from `escalation_s` in `backend/config/weights.yaml`. The `demo` profile compresses minutes into seconds.

> [!warning] High risk skips the wait
> Night, an older driver, or rising water sets `responder_flag=True` at once. The responder handoff runs in parallel with the call and does **not** wait for the drone. Drone dispatch at T+3 does not block the handoff.

## Design

- `transition(case, event, now) -> Case` is pure and immutable. Every transition appends to `case.timeline`.
- An asyncio scheduler feeds timer events into `transition`.
- Inbound replies: `POST /api/cases/{id}/reply` (driver view buttons) and a signed Photon webhook at `POST /api/photon/webhook`.
- The responder view gets location, people count, and water depth only. See [[Privacy and Consent]].

## Code

- `backend/stages/stopped.py` (planned): stop detection and state machine
- `backend/stages/escalation.py` (planned, if split out)
- `backend/api/routes_cases.py` (planned): reply endpoint
- `backend/tests/test_escalation.py` (planned, TDD)
- `backend/config/weights.yaml` (exists): `stages`, `escalation_s`

> [!note] Checkpoint 3
> A stopped driver walks through every case state in order, and each state shows up on the WS stream.

## Related

- [[Drone Dispatch]] and [[Drone Vision]]
- [[Photon Outreach]] for calls and texts
- [[Risk Scoring]] for the `responder_flag` threshold
- [[Demo Script]]
