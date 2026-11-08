---
tags: [hitide, module, scoring, tdd]
status: in-progress
updated: 2026-11-07
---

# Risk Scoring

Two parts: road status (done, TDD) and urgency score (planned, TDD).

## Road status (done)

Depth over the road in inches, classified with the NWS "Turn Around Don't Drown" table:

| Status | Depth | Meaning |
|---|---|---|
| open | < 3 in | passable |
| caution | 3 to < 6 in | slow down |
| closed | >= 6 in | closed for cars |
| float | >= 12 in | most vehicles may float |
| boat | >= 24 in | boat only |

Thresholds come from `road_status_in` in `backend/config/weights.yaml`. See [[Decisions]] (2026-11-07 entry).

Tests: 19 pass in `backend/tests/test_road_status.py`. The first commit was the RED tests, then the GREEN implementation.

## Urgency score (planned)

`urgency = sum(w_i * f_i)` over:

- flood danger: depth now, and rate of rise near the route or position (`depth 0.35`, `rise 0.15`)
- night, 8 PM to 6 AM (`night 0.10`)
- age band: 65+ up, 16-19 teen flag that notifies the parent (`age 0.12`)
- vehicle: low clearance and EV factors (`vehicle 0.08`)
- situation multiplier: planning 0.2, driving toward 0.6, stopped in water 1.0 (`situation 0.20`)
- simulated driver profile (2026-11-07, see `docs/driver-profile.md`). Additive, so it can only raise urgency:
  - self-reported evacuation need: mobility, wheelchair, powered medical equipment, cognitive support, pregnancy (`needs 0.10`). Hearing and vision needs change the alert channel, not the score.
  - new to the area (`unfamiliar 0.03`)
  - Drive Safe & Save phone-distraction rate, saturating at 2 per 100 mi (`distraction 0.04`)
  - live State Farm signal once its scripted time passes: roadside request or ADT water sensor (`signal 0.15`)

Output: a score plus `reasons[]` for the case card. A score at or above `high_risk_threshold` (0.65) sets `responder_flag`. See [[Stage 3 Stopped in water]].

## Code

- `backend/scoring/road_status.py` (exists): `RoadStatus` enum and `classify()`
- `backend/tests/test_road_status.py` (exists): 19 tests
- `backend/config/weights.yaml` (exists): all weights and thresholds
- `backend/scoring/risk.py` (exists): urgency score, reasons, and `profile_risk_fields()`
- `backend/tests/test_risk.py` (exists, TDD): includes the profile factors and the never-lowers rule

## Related

- [[Flood Simulation]] supplies depth
- [[Stage 1 Pre-trip]] and [[Stage 2 En route]] use road status
