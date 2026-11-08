---
tags: [floodwatch, module, vision]
status: done
updated: 2026-11-08
---

# Drone Vision

The drone does two jobs at a critical point (spec: `~/Downloads/drone_vision_plan.md`; ground truth: overview §9):
1. **Measure the water level.** It finds where the floodwater meets the ground. Water sits level, and the elevation map gives the ground height there, so it knows the water surface and the depth over the road, with a range.
2. **Find vehicles and people** in the water and raise prioritised alerts for an operator.

Accuracy: [[2026-11-08 Drone vision accuracy]].

## Pipeline (`backend/vision/`)

| Step | File | What it does |
|---|---|---|
| Segment | `segment.py` | SegFormer-B0 ADE20K (class ids resolved **by name**) plus zero-shot CLIPSeg "flood water", because ADE20K calls muddy water earth or road. Zero-shot water never overrides a car, person, tree or sky. Low-light flag. The blue-sheet colour fallback is off for real footage. |
| Ground grid | `camera.py`, `grid.py` | Pinhole camera with drone pose. Projects each DEM cell into the frame, checks occlusion, and takes a 5-frame **majority vote in ground space**, so drift doesn't matter. |
| Edges | `edges.py` | Keeps water→ground boundaries only where the dry side is open ground (not tree, building, car, unseen or frame edge). Sub-cell 0.5 crossing found in image space. Each edge is assigned a side of the road's low point. |
| Water level | `water_level.py`, `measure.py` | Median/MAD inliers. The range combines edge scatter, DEM error, pose × slope and mask bias × ground sample distance × slope. A level-set fit is an independent cross-check. `water_on_road` is tri-state; dry only when nothing argues otherwise. Depth at the road low point, with the road's own DEM error. |
| Rise | `rise.py` | Within a hover, Theil–Sen on block medians (the shared pose bias cancels). Across revisits, weighted fit with **each hover's own bias**. Trend reported only when significant; otherwise `unknown`/null. |
| Objects | `detect.py`, `objects.py` | YOLOv8n + ByteTrack. A track must persist 5 frames. In-water ring counts informative pixels only. A car in water is placed on the **water plane**, because its box bottom is the waterline. Depth at the vehicle = WSE − ground (null if the ground is above the water, or if there's no water surface). **The car's shape is never used as a depth gauge.** People: on_vehicle (tuned roof rule), in_water, dry_near_water (30 m). |
| Alerts | `alerts.py` | Spec §7.7 table. Drive Safe & Save case match within 50 m (one alert per incident). Boat required over 24 in, or whenever depth is unknown. `unknown` water state raises a "take a closer look" alert. |
| Spread | `spread.py` | Observed **rise** applied along the same river chain with RegionFlood's formula, so the river's slope is respected. Uses the low end of the range. Result is `likely_flooded`, never confirmed. |
| Snapshot | `snapshot.py`, `pipeline.py` | Overview §9.5 fields plus spec §8 fields. Validated, frozen. Unknowns are null. |
| In/out | `api/routes_snapshots.py`, `bridge.py`, `run_pipeline.py`, `overlay.py` | `POST /api/snapshots` → `snapshot.created` over WS, fused into the Hill Country loop. The server recomputes alerts; `X-Vision-Token` is optional. CLI for synthetic, photo and video sources. Annotated JPG. |
| Live drone | `live.py`, `drone/tello.py`, `api/routes_region.py` | `POST /api/region/drones/tello` (`DRONE_MODE=tello`): the Tello flies the leg and hovers about 15 s, keeping about 30 frames. After landing, the frames go through segmentation (with the blue-sheet colour fallback for indoors) and tracked YOLO. The result is fused and broadcast exactly like `POST /api/snapshots`. There's no GPS or elevation map, so depth is null. A hover with no water seen is `unknown`, not dry. If the models are missing, it falls back to the HSV cover. |

## Run

```
cd backend
uv sync --extra vision && uv run python scripts/fetch_vision_models.py      # once, needs network (~620 MB)
uv run python -m vision.run_pipeline --source synth:cp-0014 --at 2025-07-04T10:45:00Z --post
uv run python -m vision.run_pipeline --source images:../data/drone_samples
uv run pytest tests/test_vision_*.py -q
```

## Honest limits (say these in the pitch)

- There was **no physical drone run**. The geometry is checked on synthetic hovers with exact truth, including synthetic scenes parameterised by July 2025 replay values at real Kerrville points. Perception is a smoke test on the 8 real photos it was tuned on, which have no pose and so get no depth.
- Ordinary GPS gives about ±6–10 in. "High" confidence needs RTK-grade pose. Floods several metres deep read `low` because only steep banks contain them.
- Depth comes only from the water edge plus the elevation map. Photos, video and the indoor Tello report `depth: null`. A car-shape estimate was removed after it matched only 3/8 photo labels.
- YOLO is AGPL (fine for a hackathon; production needs a licence or another detector).
- The old manual-label flow (`assess.py`, `catalog.py`, `results.json`) is unchanged and still drives the Kerrville driver-rescue demo case.

## Related

- [[Critical Point Drones]] (where snapshots fuse), [[Drone Dispatch]], [[Stage 3 Stopped in water]]
