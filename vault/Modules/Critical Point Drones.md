---
tags: [floodwatch, module, drone, critical-points]
status: done
updated: 2026-11-08
---

# Critical Point Drones (Hill Country)

The overview's core idea (§8): drones fly short trips to the few **critical points** whole communities depend on, and only when our data about them is uncertain. It runs on a replay of the **real July 4, 2025 flood** over Hunt → Ingram → Kerrville. Full math: `docs/drone-critical-points.md`.

## The loop (overview §8.5)

`belief (gauges only) → p_flooded per crossing → chokepoints per area (cut test) → priority → multi-drone tours → fly first leg → snapshot (from replay truth) → p, cuts and priorities change → re-plan`

| Piece | Code | Tests |
|---|---|---|
| Region cache (OSM, 3DEP, waterways, places) | `backend/scripts/build_region_cache.py`, `sim/region.py` | |
| Real hydrographs (5 USGS gauges) | `scripts/fetch_july2025.py` | |
| HAND replay flood: truth vs causal belief | `sim/hand_flood.py`, `sim/region_flood.py` | `test_hand_flood.py` (10) |
| Fusion → p_flooded (overview §6.3–§6.4) | `fusion/segment_status.py` | `test_fusion.py` (11) |
| Chokepoints (k routes + exact cut), truck access | `critical/access.py` | `test_critical_access.py` (8) |
| Priority (overview §8.4) | `critical/score.py` | `test_critical_score.py` (9) |
| Area risk score, low → high ground | `critical/area_risk.py` | `test_area_risk.py` (9) |
| Drone tours (orienteering, battery, terrain AGL) | `drone/planner.py` | `test_drone_planner.py` (8) |
| Route out + safety wording (overview §10.2–§10.3) | `routing/instructions.py` | `test_route_out.py` (6) |
| Loop, demo runner, API | `critical/loop.py`, `demo/hill_country.py`, `api/routes_region.py` | `test_hill_country_demo.py` |

## How it relates to the colleague's evidence module

`backend/evidence/analysis.py` (feat/frontend) asks, per hand-configured community: "remove one uncertain crossing; does it lose all modeled exits?" We use exactly that cut test, `reachable(blocked=c)`, per *area*, on real population nodes. Its "1000 × affected communities" heuristic becomes the continuous `dependency` term of the overview's priority. The evidence store, with provenance and the operator inspection loop, is unchanged. Wiring drone snapshots into it as `kind="drone"` observations is the next integration step.

## Related

- [[Drone Dispatch]] (Kerrville stopped-car flight)
- [[Drone Vision]], [[Risk Scoring]], [[Flood Simulation]]
- [[2026-11-08 July 2025 replay calibration]]
- [[Decisions]]
