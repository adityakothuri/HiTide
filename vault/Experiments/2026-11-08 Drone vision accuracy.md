---
tags: [hitide, experiment, vision]
status: done
updated: 2026-11-08
---

# Drone vision accuracy (2026-11-08)

How well the drone vision pipeline ([[Drone Vision]]) measures water, against three kinds of ground truth.

There was no physical Tello or tabletop scene. That means:

- **Geometry** (water edge to water surface to depth) is checked on synthetic hovers with exact truth. Some of those hovers are synthetic scenes parameterised with values from the **July 4, 2025 replay**: real road elevation and the gauge-driven rise. They do not replay real imagery.
- **Perception** (segmentation, YOLO, people) is smoke-tested on the 8 real flood photos in `data/drone_samples/`. The same 8 photos were used to tune the prompts and thresholds, and there is no held-out set.
- **Depth comes only from the water edge plus the elevation map.** Photos, video and live Tello frames have no pose or elevation map, so they report `depth: null`. A car's shape is never used as a depth gauge (removed 2026-11-08).

Limits of the synthetic checks:
- The renderer reuses the camera and grid code. A hand-computed projection test (`test_oblique_projection_matches_hand_computed_pinhole_values`) pins that code to the pinhole maths, so a convention bug can't cancel out between renderer and estimator.
- The DEM given to the estimator is exact.
- These are not modelled: lens distortion, timing lag, a sloped water surface, vegetation, or non-uniform segmentation errors such as reflections or mud read as road.

Reproduce:
```
cd backend && uv run pytest tests/test_vision_*.py -q
```
The exact numbers below come from probe scripts run during development (not committed). The tests assert looser thresholds, given next to each table.

## 1. Geometry on synthetic truth (`tests/test_vision_water_level.py`)

Scene: a river valley with a road dipping to the bed. The camera is 55 m above ground and looks 52° down, at 320×240 px. All results are on the water surface elevation (WSE).

| Condition | Median error | P95 error | Truth inside reported range |
|---|---|---|---|
| Noise-free self-consistency (same camera model and grid as the estimator), any depth 0.3–1.5 m | ≤ 0.3 cm | ≤ 0.3 cm | n/a |
| Independent per-frame pose noise (1 m / 0.5°) | 1.0–2.2 cm | 2.4–12 cm | 100% |
| **Hover-long GPS/gimbal bias** (1 m / 0.5° / 0.5 m z) + ±2 px mask bias + 5% flicker, gentle banks (6%) | 3.8 cm | 14.9 cm | 100% |
| same, moderate banks (12%) | 6.1 cm | 26.3 cm | 100% |
| same, steep banks (25%) | 15.4 cm | 42.3 cm | 100% (all marked `low`) |

The test asserts truth inside the range in **≥ 90%** of 40 trials, P95 ≤ 30 cm and median ≤ 10 cm, on one scene (0.8 m deep, 12% bank). "100%" means 40/40 under the modelled noise; with 40 trials the true rate could be as low as about 91%. The range only covers noise the model knows about, because its sigma includes the same pose and mask terms the test injects.

What this means:
- With ordinary GPS (about 1 m), expect about **±6–10 in** on gentle to moderate banks. The reported range is honest: the truth was inside it in every trial. Confidence correctly reads medium or low.
- "High" needs RTK-grade pose (about 5 cm), and that is the production recommendation.
- Within one hover, rise rate is immune to the pose bias, because every estimate is shifted equally.
- **Across revisits each hover has its own bias.** Tests use 10 cm per hover with 3 hovers 10 min apart:
  - still water reads rising ≤5% of the time;
  - 60 in/hr is caught ≥90% of the time;
  - 6 in/hr is honestly `unknown`, but caught ≥90% of the time with RTK-grade pose (0.5 cm).

## 2. Synthetic scenes at Kerrville critical points, parameterised by the July 2025 replay (`tests/test_vision_kerrville_replay.py`)

Setup:
- The scene uses the critical point's real road elevation (3DEP) and the river's normal-flow surface.
- The flood is the July 4, 2025 gauge-driven truth from `RegionFlood`.
- Only the local terrain shape and the frames are synthetic. The pose carries a hover-long bias.

Points are a deterministic, evenly spaced sample of 8 per time. The terrain is a synthetic valley whose bank slope is raised until the flood fits. The test asserts ≥ 85% inside the range, with at least 6 points measured.

| Time (UTC / CDT) | Eligible flooded points | Measured | Truth inside range | Median error | Max error |
|---|---|---|---|---|---|
| 10:45 / 05:45 | 43 | 8/8 sampled | **8/8** | 2.3 in | 6.4 in (on 342 in) |
| 11:45 / 06:45 (Kerrville crest) | 32 | 8/8 sampled | **8/8** | 1.2 in | 9.8 in (on 268 in) |

- Every flooded point was flagged `water_on_road = true`.
- At 06:00 UTC (before the flood) 5/5 points came out dry or unknown. None was called flooded.
- All confidences are `low`, because floods of several metres need steep banks to stay in a 120 m window, and the ranges widen honestly.

## 3. Real flood photos (`tests/test_vision_segment.py`, `run_pipeline --source images:`). Smoke test on the tuning set, with no depth truth

| Check | Result |
|---|---|
| Water found (overview §22) | **7/8**. flood_08 (night, wet asphalt car park) is missed by both models and reported as `water_on_road: null`, never `false`. |
| SegFormer-B0 ADE20K alone | 4/8. It calls muddy floodwater `earth` / `road` / `dirt track`. That is why a zero-shot CLIPSeg "flood water" layer was added. |
| Person on a car roof (flood_01–03) | **3/3** `on_vehicle` → critical alert. Uses the repo's tuned roof rule (45% band + seated). |
| Depth on photos | `null` for all 8. A photo has no pose or elevation, and the car's shape is not used. (Before 2026-11-08, a car-shape band scored only 3/8 against `labels.json`, which is why it was removed.) |
| Speed (M-series, MPS) | SegFormer 0.14 s/frame; CLIPSeg about 2.2 s, run every 5th frame. |

The conclusion for the pitch: **numeric depth comes only from the water edge plus the elevation map.** Cars and people produce alerts, never a depth. When depth is unknown, any person or vehicle in the water gets `boat_required`.

## Stress findings that changed the design

1. The spec's per-pixel mask vote breaks while the drone drifts. Voting moved to a **ground grid**.
2. The spec's flat homography adds bank-parallax error. It was replaced with a **full camera model projecting DEM cells**.
3. A biased segmentation boundary reads low (or high) on **both** banks, and the level-set cross-check can't see it. An explicit mask-bias term was added to the range.
4. MAD = 0 on quantized DEMs. A floor was added.
5. A road fraction is the wrong wet test: a 12 in dip covered 9.6% of a 120 m road. The test moved to **wet area ≥ 6 m²**, and `road_covered_pct` is still reported.
6. A car's box bottom in water is its **waterline**. The car is placed on the plane z = WSE, not on the DEM, which would put it behind its true spot.
7. "Spread to cells below the WSE within 1 km" ignores the river's slope. The **rise** is spread along the river chain with RegionFlood's formula.
8. One 25 s hover rarely proves a rise. `rising` is reported only when the 95% interval clears the threshold. An unknown trend reports **no rate**: a noisy 5-frame series had produced "4,970 in/hr" and crashed the schema.
9. Reflections around floating cars are labelled car/tree, so the in-water ring now counts only informative pixels.
10. A wet snapshot with no depth crashed the critical-point loop (`None >= 24`). The bridge now stores the loop's own 0.0 convention, and the honest null still goes out over the API.

## Fixed after review (python, fastapi and code reviewers)

11. **Rise across revisits** used one bias for all hovers. Each flight's own bias read as about 24 in/hr. Fixed with a per-hover weighted fit.
12. **Dry road** could be reported:
    - with a wet vehicle present, in low light, or on a coarse mask;
    - while the measured surface was above the road;
    - with water cells below 0.5 probability counted as "seen dry".

    `false` now requires that nothing argues otherwise.
13. The **depth range** left out the road's own DEM error. It is now added in quadrature.
14. (Historical) Car-reference "wheels" sat on the vehicles_float line. Car-shape depth has since been removed entirely.
15. **Off-frame boxes** wrapped numpy slices and read unrelated pixels. Bounds are now clamped, and NaN boxes are rejected.
16. NaN water-surface values poisoned the rise series. Absurd rates are now `unknown`. The mask-bias ground sample distance now includes the oblique stretch. "High" now needs the cross-check and ≥60% inlier edges.

## Audit 2026-11-08 (after car-shape depth removal)

Three independent reviews covered the geometry maths, the perception, alerts and bridge code, and how honest this evaluation is. Fixed:
- A person in the water with unknown depth now needs a boat. A vehicle "in water" on ground above the water surface gets **no depth** instead of 0 in.
- A vehicle or person with no informative pixels around it (frame edge, crowd) is `unknown`, never "dry". It raises a medium "take a closer look" alert.
- An occupied car matching a Drive Safe & Save case raises **one** critical alert that carries the case, instead of two.
- Live hovers no longer reuse the previous hover's zero-shot mask or ByteTrack tracks. Objects come from the union of the last 5 frames.
- A Tello flight whose vision step fails falls back to the HSV result, so the flight is never lost.
- `POST /api/snapshots` recomputes alerts on the server and accepts an optional `X-Vision-Token`.
- The loop API publishes `est_depth_in: null`, not 0, for snapshots with no measured depth.
- Geometry (verified with probe scripts by the reviewer, now regression-tested):
  - A road is called dry only if its **lowest 10% of cells** were seen. A 14 in puddle in a dip under a tree had been reported dry.
  - "Two sides" now means **two banks**, judged by which way each edge faces from water to ground, not the two ends of the road. A road running along the river had claimed two sides from one bank.
  - Each bank is fitted on its own and the surface is the mean of the two. A sideways GPS offset used to make the pooled MAD drop one bank.
  - The range now includes altitude error (dz/tan of the grazing angle) and the oblique stretch of attitude error. The coverage test now runs both looking **along** and **across** the river.
  - The rise tracker starts a new visit when the reported pose moves or drifts more than 1 m (0.5 m vertically). A revisit 45 s later with a new 10 cm bias had read "rising 206 in/hr".
- Wording in this note is corrected as above: "self-consistency", "parameterised by", "smoke test", and the thresholds the tests assert.
