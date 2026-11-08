---
tags: [floodwatch, module, drone-vision, tabletop, cad]
status: built-synthetic-validated
updated: 2026-11-08
---

# Tabletop Model

A 3D-printed tray of downtown Kerrville that holds real, dyed water. The drone camera measures the water rise, and the CAD heightmap is the exact ground truth, so we can score the [[Drone Vision]] pipeline physically instead of only on synthetic valleys.

## What is printed

| | |
|---|---|
| Area | 1.2 × 1.2 km around downtown Kerrville. It covers the Guadalupe River, the Sidney Baker bridge (cp-0154) and the Quinlan Creek crossings (cp-0043 Park Street). |
| Source | `data/town/dem10.npz` (USGS 3DEP 10 m DEM), OSM roads and river from `data/town/`, building centroids from `data/region/hill_country/places.json`. |
| Scale | 220 mm map, 1:5455 horizontal, **3× vertical**. **0.55 mm on the print = 1 world metre.** |
| Tray | 236 × 236 × 25.8 mm. 8 mm rim walls. A 4 mm base at the lowest ground. The Guadalupe channel is carved 1 m (world) below low flow, so it holds water at rise 0. |
| Bodies | `terrain.stl` (tray, watertight, 451k triangles); `roads.stl` (230 ribbons 0.4 mm proud of the ground, a second colour); `buildings.stl` (111 blocks, a third colour); `terrain_lowpoly.stl` (29k triangles, for Fusion's mesh-to-BRep) |
| Fiducials | Four ArUco tags (`DICT_4X4_50`, ids 0–3 = SW, SE, NE, NW), 20 mm, on 24 mm corner pads flush with the rim top. Print `fiducials_print.png` at 300 dpi and 100 %. Glue each tag with its top edge facing north (the +y side of the print). |
| Stations | **cp-0154** Sidney Baker bridge: Guadalupe edge, readable at every level. **cp-0043** Park Street crossing: dry until the tray water overtops the Quinlan sill at about 11.5 m. |

## Ground truth

- Water in a tray is level, so truth is a **bathtub fill of the CAD heightmap connected to the river** (`sim/print_scale.py`). A sealed hollow stays dry until it is overtopped.
- `volume_curve.json` turns a poured volume into a level and a rise:

| World rise | Water level on the print | Poured into the empty tray |
|---|---|---|
| 0 m | 4.55 mm | 0.8 mL |
| 3 m | 6.2 mm | 4.3 mL |
| 6 m | 7.8 mm | 13.4 mL |
| 9 m | 9.5 mm | 28.3 mL |
| 12 m | 11.1 mm | 48.6 mL |
| 15 m | 12.8 mm | 90.0 mL |

- Road depth truth is the level minus the road surface, counted only where the water actually reaches the road.

## How the pipeline runs on it

Code: `vision/tabletop.py` and `vision/fiducials.py`.

- **"ex" frame.** The print is divided uniformly by `mm_per_m`.
  - A uniform scale keeps the camera geometry exact.
  - Horizontal ex metres are world metres, so road widths and areas in `vision.yaml` still mean what they say.
  - Heights carry the 3×. `PrintScale.world_from_ex` removes it at the end.
- **Pose.** ArUco detection plus `cv2.solvePnP` against the CAD tag corners. No GPS.
- **Water mask.** HSV blue (dyed water) through the existing `color_fallback`. The plastic carries no ADE20K meaning.
- **Blockers.** The CAD building blocks and the rim are projected into each frame as `building`. Water against a wall says nothing about the level. Without this, a 1 px mask bias read +3.7 m at Park Street.
- **Error budget.** The `tabletop:` section of `config/vision.yaml` sets print error 0.1 mm, PnP 0.5 mm / 0.2°, and mask bias 1.5 px.

## Run

```bash
cd backend
uv run python -m scripts.build_print_model                    # ~8 s; --exaggeration 5 / --crop-m 900 to rescale
uv run python -m scripts.run_tabletop --source synth --rise 3,6,9,12,13
uv run python -m scripts.run_tabletop --source images:<dir> --poured-ml 48.6   # or --level-mm 11.1
uv run python -m scripts.run_tabletop --source tello --level-mm 11.1          # stream only, never takes off
uv run python -m scripts.check_print_export <fusion_export.stl>              # Fusion didn't reshape the terrain
uv run pytest tests/test_print_scale.py tests/test_tabletop.py
```

Every run appends measured and truth values to `data/print_model/runs.jsonl`.

## Print and pour runbook

1. **Print** `terrain.stl` in PETG.
   - 0.12 mm layers.
   - 4 walls and 5 bottom layers.
   - Optionally print `roads.stl` and `buildings.stl` as extra parts in grey and white.
2. **Seal it.** Brush on a thin clear coat or epoxy, then let it cure. FDM prints weep through pinholes.
3. **Glue the four tags** on the corner pads, top edge facing north. The tags are what make depth possible: no tags, no pose.
4. **Mix the water.** Use tap water, blue food dye and **one drop of dish soap**.
   - The soap matters: at 0.55 mm per metre, surface tension decides where a thin water edge stops.
5. **Pour** with a 10 mL syringe, following the table above.
   - **The primary truth is a caliper depth reading on the flat channel floor**: the floor is at 4.00 mm, so level = floor + depth.
   - The pour volume is the cross-check.
6. **Capture** with the camera about 35–40 cm above the tray, looking north, with all four tags in frame.
   - Use a phone in `images:` mode, or the Tello streaming while held or mounted. Pass `--mirror` with a 45° mirror clip.
   - **Calibrate the camera first** and pass `--camera calib.json` with `{fx, fy, cx, cy, width, height, dist}` from `cv2.calibrateCamera` on a checkerboard.
   - Without calibration the run uses the nominal Tello 82.6° diagonal FOV and prints a warning.
   - A pose needs at least 2 tags in frame and a reprojection RMS of 1.5 px or less; otherwise the frame is dropped.

## Fusion 360 via MCP

- `.mcp.json` registers `fusion` at `http://127.0.0.1:27182/mcp`, the same add-in as `~/dome/dome_cad`.
- With the add-in running:
  1. Import `terrain_lowpoly.stl` and convert it from mesh to BRep.
  2. Import `roads.stl` and `buildings.stl` as bodies.
  3. Add only rim or base features.
  4. Export STL, 3MF and STEP.
- **Fusion must not reshape the terrain.** `check_print_export` compares the footprint, rim top and sampled terrain heights against `truth.npz`.
  - The generated `terrain.stl` and `terrain_lowpoly.stl` both pass.

## Limits

- The synthetic numbers only validate geometry: there is no lens distortion, meniscus or lighting.
  - Results: [[2026-11-08 Tabletop synthetic accuracy]].
- **Steep banks dominate the error.** The Sidney Baker bluff (×3) turns 1 px of mask bias into about 1.5 m.
  - The ranges are honest (truth was inside every one), but readings there stay `low`.
  - Gentle Park Street reads within 0.2 m.
- **Overtop transition.** Just as water spills into a sealed valley (Park Street near 11 m), the pipeline's "locally level" assumption can claim depth over a road the water has not reached yet.
- Buildings are centroid squares, not footprints; the offline cache has no polygons.
- Bridges are not printed. The road ribbon stops at the channel, so the river flows freely.
