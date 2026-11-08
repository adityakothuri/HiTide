---
tags: [floodwatch, testing, tdd]
status: done
updated: 2026-11-07
---

# TDD Evidence

Written per the ECC `tdd-workflow` skill (Step 8). Source plan: `/Users/sandhyakothuri/.claude/plans/pasted-content-id-70ba-project-breezy-rivest.md`, with the planner breakdowns noted in [[Tooling]]. Runner: `cd backend && uv run pytest -q`.

## User journeys

1. As a State Farm driver planning a trip during a flash flood warning, I get a text with a safer route before I leave, and my parent gets a copy if I'm a teen.
2. As a driver heading toward a flooded road, my app tells me "Turn around" and reroutes me. I never get a text while I'm driving.
3. As an older driver stalled in floodwater at night, Flood Watch calls me, then my family, flags responders and sends a drone. "Not safe" never closes my case.
4. As a responder, I see only location, number of people and water depth.

## Task report

Each row has a RED commit (the test fails because the code is missing or wrong), then a GREEN commit, on branch `feat/backend-sim`.

| Behaviour | RED evidence | GREEN evidence |
|---|---|---|
| Road status from NWS depth thresholds | `0e41253` ModuleNotFoundError `scoring.road_status` | `b11b7bf` 19 passed |
| Flood depth model | `test: flood depth model tests (RED)` ImportError | `feat: flood depth model (GREEN: 27 passed)` |
| Driver urgency score | `test: risk scoring tests (RED)` collection error | `feat: driver urgency scoring (GREEN: 39 passed)` |
| Pre-trip route check + en-route lookahead | `test: pre-trip route check ... (RED)` ImportError | `feat: pre-trip route check ... (GREEN)` 49 passed |
| Stop detection + escalation state machine | ModuleNotFoundError `stages.stop_detect` (`tdd-guide` agent) | 69 passed |
| Outreach moving-driver guard + allowlist | `cannot import name 'photon_spectrum'` (`tdd-guide` agent) | 47 passed, then 165 for the suite |
| Inbound reply parsing (negations) | `test: inbound reply parsing (RED)` ImportError | 20 passed |
| Risk reasons never expose exact age/vehicle | `f637c76` 2 failed | `015ae5d` 13 passed |

## Test specification

| # | What is guaranteed | Test | Type |
|---|---|---|---|
| 1 | Depth → open / caution / closed / float / boat exactly at 3 / 6 / 12 / 24 in; NaN and negative depths are open | `tests/test_road_status.py` | unit |
| 2 | Water rises linearly, caps at the crest, decays with distance and never goes negative | `tests/test_flood.py` | unit |
| 3 | Urgency ordering: deeper, rising, night, older, low clearance and stopped all rank higher; teens notify a parent | `tests/test_risk.py` | unit |
| 4 | Reasons use coarse bands only, never "age 78" or a vehicle model | `tests/test_risk.py::test_reasons_never_expose_exact_age_or_vehicle_model` | unit |
| 5 | Moving drivers never get pre-trip warnings; one warning per alert; caution-only routes warn without blocking | `tests/test_route_check.py` | unit |
| 6 | Lookahead finds the first closed edge within 800 m and ignores caution or far hazards | `tests/test_route_check.py` | unit |
| 7 | Stopped means speed < 0.5 m/s for at least stop_seconds, away from the destination, in at least caution-depth water | `tests/test_stop_detect.py` | unit |
| 8 | Case moves forward through every state, never downgrades; safe resolves, need_help escalates; high risk is flagged at open | `tests/test_escalation.py` | unit |
| 9 | Text, poll and voice to a physically moving driver are blocked; only `env:DEMO_PHONE_*` numbers are ever really sent to; logs have no numbers | `tests/test_outreach_guard.py`, `test_outreach_adapters.py` | unit |
| 10 | "not safe", "unsafe" and "not ok" mean need_help; help always wins | `tests/test_reply_parse.py` | unit |
| 11 | Roof, inside, water and shore placement rules; the water level is a manual label | `tests/test_vision_assess.py` | unit |
| 12 | Full demo flow: A warned (plus teen parent), B turned around and rerouted with no texts, D's case reaches responders with vision "boat required" | `tests/test_demo_flow.py` | integration |
| 13 | Every emitted WS event validates against `api/schemas.py`, the frontend contract | `tests/test_demo_flow.py::test_every_event_matches_the_frontend_contract` | contract |
| 14 | No phone numbers, `env:` references or exact age in any event | `tests/test_demo_flow.py::test_no_phone_numbers_or_exact_age_in_any_event` | integration |

## Coverage

`uv run pytest --cov=scoring --cov=stages --cov=sim --cov=outreach --cov=drone --cov=vision` gives **200 passed, 90% total**.
- Core modules (risk, road status, flood, escalation, stop detection, route check, outreach, replies) are at 98–100%.
- `stages/runner.py` 85%, `sim/movement.py` 94%, `sim/engine.py` 77%.

**Known gaps:**
- `vision/detect.py` and `scripts/run_vision_batch.py` need YOLO weights and run offline ahead of time.
- The live Photon and ElevenLabs paths are unit-tested with mocked HTTP only, because we have no creds yet.
- API routes are verified manually with curl (inbound auth, origin guard), not with automated tests.
