# Plan: read flood depth from the gauge tray with the Tello camera

Status: approved for build 2026-11-08. Branch `feat/gauge-water-level` (from `feat/tello-drone`).

## Goal

Point the Tello's camera at the printed gauge tray (`backend/scripts/build_gauge_tray.py`,
`data/gauge_tray_160/`, 160 mm build), pour dyed water in, and have Flood Watch report the flood
level in **feet** with an honest range and confidence, plus what it means: is the low-water crossing
flooded, how high is the water on the stranded car (`none / wheels / doors / windows / roof`, the
existing `VisionResult.water_level` vocabulary), how many houses are flooded. Show it live on the
Tello dashboard HUD and in the ops console's Live drone panel.

## Why the tray makes this tractable

The camera never estimates depth from appearance. The tray is the measuring instrument:

- **Known geometry.** `truth.npz` holds `height_mm[iy, ix]` (501x501, `res_mm` 0.32) with
  `x = ix * res_mm`, `y = iy * res_mm`, z up, the same frame as the STL and the tag corners.
- **Known levels.** Terraces every `step_mm` = 2.0 mm, and each step is 1 ft of rise. Flood level
  in feet = `(level_mm - pool_mm) / step_mm`, with `pool_mm` 4.0 = 0 ft. The pour table gives the
  mL and wet fraction per level.
- **Known landmarks.** Road deck 4.6 mm; car road 6.98, body top 8.98, roof 10.38; house ground levels.
- **Pose for free.** Four ArUco tags (`DICT_4X4_50`, 16 mm) on corner pads, all at z = 21.6 mm,
  with corner coordinates in the manifest. Their pixel positions give the camera pose (solvePnP).
- **Water is flat.** One unknown (the level L) explains the whole wet/dry pattern: every visible
  cell with ground height < L is wet, everything above is dry.

## Pipeline (per frame)

1. **Detect tags** (cv2.aruco, `DICT_4X4_50`). Need at least 3 of the 4 IDs.
2. **Pose.** Use the 4 tag **centres** (robust if a sticker is rotated) for an IPPE solve, then refine
   with all corners when the corner order agrees (reprojection error lower). Report
   `reproj_err_px`. Reject if the error exceeds the threshold.
3. **Intrinsics.** Default Tello 960x720: fx = fy = 920, cx = 480, cy = 360, no distortion. Optional
   `estimate_focal()` from the tag plane (single-view calibration with the principal point fixed),
   saved to `~/tello-test/gauge_camera.json`. Configurable via env `GAUGE_CAMERA_JSON`.
4. **Drape.** Project every Nth heightmap cell (stride configurable, about 1 mm) at its ground
   height into the image. A z-buffer marks the cells **visible** from this pose; houses and terraces
   occlude at oblique angles. Exclude the tag pads, rim and out-of-frame cells.
5. **Wetness per visible cell**, from 0 to 1:
   - **With a dry baseline** (captured before pouring, same pose within tolerance): colour change
     in CIE Lab versus the baseline drape, plus a dye-hue prior. This is the primary mode, and it is
     robust to any filament colour.
   - **Without a baseline:** dye-hue prior only (default blue; `GAUGE_DYE` = blue/green/red). Confidence
     is capped lower.
6. **Level fit.** Score candidate L from `floor_mm` to `rim_top_mm` in 0.25 mm steps: the agreement
   between predicted wet (height < L) and observed wetness over visible cells, weighted to
   emphasise the cells near the candidate waterline. Best L plus a range (all L within a score margin).
   Return **None with a reason** when evidence is weak: fewer than 3 tags, high reprojection error,
   too few visible cells, or a flat score.
7. **Temporal smoothing** (`update()`): median of the last 8 valid single-frame levels, range from
   their spread, so hover jitter and glare flicker don't jump the reading.
8. **Meaning:** `ft` and `ft_range`; `crossing_flooded` = L > road deck; `car_level` from the car
   heights (none < road; wheels < road + 1.0; doors < body top; windows < roof; roof otherwise);
   `houses_flooded` = count with ground < L.

Honesty rules (as in Aditya's vision work on `feat/safety-core`): a number is always reported with a
range, weak evidence returns None rather than a guess, and synthetic frames are labelled.

## Module layout (new, self-contained, no clash with `backend/vision/` on other branches)

`backend/gauge/` needs only numpy and cv2, so it runs inside the Tello bridge venv (`~/tello-env`);
the backend venv has no OpenCV. Tests live in `backend/gauge/tests/` and run with
`cd backend && ~/tello-env/Scripts/python.exe -m pytest gauge/tests -q`. Each test module starts with
`pytest.importorskip("cv2")` so the normal backend suite is unaffected.

| File | Public API |
|---|---|
| `gauge/model.py` | `GaugeLevel(ft, level_mm, ml, wet_fraction)`; `TrayModel` (frozen: `directory, name, res_mm, height_mm, river, size_mm, floor_mm, pool_mm, step_mm, rim_top_mm, levels, tag_corners_mm: dict[int, (4,3)], tag_dictionary, tag_mm, road, car, houses`); `load_tray(directory=None)` (default env `GAUGE_TRAY_DIR`, else `data/gauge_tray_160`); `level_ft(model, mm)`, `level_mm(model, ft)` |
| `gauge/camera.py` | `Intrinsics(fx, fy, cx, cy, dist=(0,0,0,0,0))`, `tello_default(width=960, height=720)`, `load_intrinsics()`; `Pose(rvec, tvec)` (cv2 convention, tray mm to camera); `project(points_mm, cam, pose) -> (px (N,2), depth_mm (N,))`; `camera_position_mm(pose)` |
| `gauge/pose.py` | `detect_tags(frame_bgr, dictionary) -> dict[int, (4,2)]`; `PoseFix(pose, reproj_err_px, tag_ids, camera_mm)`; `solve_pose(seen, model, cam) -> PoseFix or None`; `estimate_focal(seen, model, width, height) -> float or None` |
| `gauge/synth.py` | Test rig and offline demo, independent of the estimator (ray-casts into terrain and the water plane): `look_at_pose(model, distance_mm, elevation_deg, azimuth_deg, target_mm=None, roll_deg=0)`; `render(model, cam, pose, level_mm=None, *, filament_bgr, dye_bgr, dye_alpha, noise=Noise(), rng=None) -> frame_bgr`; draws ArUco tags on the pads; `Noise(blur_px, gauss_sigma, jpeg_quality, brightness, glare_blobs, pose_jitter_deg)` |
| `gauge/water.py` | `WaterEstimate` (frozen, `to_dict()`): `level_mm, level_mm_range, ft, ft_range, confidence, crossing_flooded, car_level, houses_flooded, houses_total, visible_cells, wet_cells, tags_seen, reproj_err_px, has_baseline, simulated, reason, ts`; `GaugeReader(model, cam=None, dye="blue")` with `set_baseline(frame) -> (ok, reason)`, `read(frame) -> WaterEstimate`, `update(frame) -> WaterEstimate` (smoothed), `reset()`, `overlay(frame, estimate) -> frame_bgr` (tags, wet cells tinted, level text) |
| `gauge/demo.py` | `python -m gauge.demo --level-ft 3 [--elevation 50] [--out file.png]`: render, then read, then write an overlay PNG and print the estimate (slides and offline demo) |

## Physical setup (deliverable: `docs/gauge-tray-setup.md` + `backend/scripts/gauge_tag_sheet.py`)

- **Tag sheet:** a PNG at 600 dpi with the four 16.0 mm DICT_4X4_50 markers (IDs 0-3), a white quiet
  zone, an orientation arrow (+Y, toward tags 2 and 3), cut lines and a 50 mm scale bar to check the
  printer didn't rescale. Written to `data/gauge_tray_160/tag_sheet.png`.
- Stick tag *i* on the pad at the manifest's `centre_mm` (0 at x,y = low/low; 1 at high-x; 2 at
  high/high; 3 at high-y).
- **Water:** strong blue food dye (or set `GAUGE_DYE`). Pour volumes per foot come from the pour table.
- **Camera placement.** The Tello camera faces forward and can't tilt, so for a steep view
  **prop the Tello nose-down about 45° on a stand** (motors off, video only). This is the reliable
  demo mode, and it sidesteps the worn battery. Hover mode works at shallow angles with lower
  confidence. Distance 300-450 mm keeps the tags at 30 px or more.
- Lighting: bright, diffuse, no direct glare on the water. Matte filament helps.

## Integration

- **Bridge** (`backend/scripts/tello_dashboard.py`): a `GaugeService` thread runs `GaugeReader.update`
  on the latest frame at about 2 Hz while enabled. Routes: `GET /gauge/status`,
  `POST /gauge/baseline`, `POST /gauge/start`, `POST /gauge/stop`, `GET /gauge/overlay.jpg`. A HUD card
  shows the level in ft, the car level, the crossing, confidence, and buttons.
- **Backend** (`backend/api/live_drone.py`): forwards `/api/live-drone/gauge` (status),
  `/api/live-drone/gauge/{baseline|start|stop}` (POST, trusted origin), and
  `/api/live-drone/gauge/overlay.jpg`. Offline bridge means `{"gauge": "offline"}`.
- **Contract first:** `docs/api-contract.md` gets a "Gauge tray water level" section.
- **Console** (`frontend/src/evidence/LiveDronePanel.tsx`): a gauge card with the big ft reading
  plus range, car level, crossing, houses, confidence, and Capture dry baseline / Start / Stop buttons.

## Verification

- Synthetic sweep (pytest): levels 0-7 ft, elevation 35-65° (stand) and 20-25° (hover), azimuth
  0-360°, distance 300-600 mm, with noise. Target: |error| ≤ 0.5 ft in at least 90% of stand-mode
  cases with a baseline, ≤ 1 ft without; None (not a wrong number) when tags are hidden or
  occlusion is extreme.
- Pose accuracy: camera position within 10 mm at 400 mm.
- Bridge and backend: route tests with fakes; console: tsc, lint, vitest.
- End to end: `gauge.demo` renders feed through the bridge in fake mode, then the backend, then the
  console card (browser check).
- Real tray: run with the printed tray once available (not blocking).

## Execution (ECC harness agents)

1. **Wave 1, in parallel:** (A) `tdd-guide` builds `gauge/` model, camera, pose, synth, water, demo
   and tests; (C) `general-purpose` builds the tag sheet script and setup doc. Disjoint files.
2. **Wave 2:** (D) `general-purpose` integrates bridge, backend, contract and console against the
   API above, after A lands.
3. **Wave 3, in parallel reviews:** `python-reviewer`, `code-reviewer`, `security-reviewer`, then fixes.
4. Final end-to-end verification, docs (handoff, vault), commit and push.
