---
tags: [floodwatch, module, vision]
status: todo
updated: 2026-11-07
---

# Drone Vision

Runs YOLO on public flood aerial images ahead of time, then applies rules to place people relative to the car and estimate water level.

## Pipeline

1. Collect 6 to 10 public flood aerial images into `data/drone_samples/`. Record sources in `data/drone_samples/sources.md` (see [[Data Sources]]).
2. `scripts/run_vision_batch.py` runs ultralytics YOLOv8n (COCO person and car) offline. Output: boxes JSON and an annotated JPG, served from `/static/drone/`.
3. `vision/assess.py` applies the rules below and writes the result.

## Rules

- **Water level**: from a manual label in `labels.json`. Always marked `"source": "manual"` in the output.
- **Person placement**: from box overlap with the car box. Top half of the car box means "on roof". Outside the car box means "in water or shore".

## Night mode

A pre-rendered pseudo-thermal frame (OpenCV colormap on a grayscale image), flagged `simulated: true`. Never presented as real thermal.

> [!warning] Demo honesty
> Water level is manual. Night thermal is simulated. Say so in the demo. Do not claim YOLO measured depth.

## Code

- `backend/vision/__init__.py` (exists, empty)
- `backend/vision/detect.py` (planned): YOLOv8n wrapper
- `backend/vision/assess.py` (planned): placement and water-level rules
- `backend/scripts/run_vision_batch.py` (planned)
- `data/drone_samples/` (exists, empty): images, `sources.md`, `labels.json` still to add

## Related

- [[Drone Dispatch]] for when the drone arrives
- [[Stage 3 Stopped in water]] for the Verified state

## Implementation (2026-11-07)

- Model: pretrained **YOLOv8n** (COCO: person, car, truck, bus, boat), run **offline ahead of time** by `backend/scripts/run_vision_batch.py`. The live demo never runs a model.
- Detection: `backend/vision/detect.py` (conf ≥ 0.25, 1280 px, merges overlapping car and truck boxes).
- Rules: `backend/vision/assess.py`. A person counts as **on roof** if their box overlaps a car horizontally and their feet are in the top 45% of it, or if they are seated at the roof line. Mostly inside the car box means inside_unknown, otherwise in_water. Water level comes from a **manual label** (`data/drone_samples/labels.json`), and the UI shows it as manual.
- Lookup: `backend/vision/catalog.py` serves the precomputed `data/drone_samples/results.json`.
- Night: the main image is a **simulated thermal** frame (`flood_01_thermal.jpg`, INFERNO colormap, stamped "SIMULATED THERMAL").
- Demo image: `flood_01.jpg`, from the Toowoomba flash flood (Wikimedia Commons, CC BY 2.0). One person was **really detected on the roof** at confidence 0.74, with water at the windows. Three bystanders on the far bank are dropped from the demo case (flagged in labels.json).
- Images: 8 total, all license-checked. See `data/drone_samples/sources.md` and [[Data Sources]]. They are ground or elevated shots, not true top-down drone frames, which we say honestly in the pitch.
- Recommendation: see [[2026-11-07 Bridge elevation fix]].

