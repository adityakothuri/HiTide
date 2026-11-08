# Agent handoff: Tello drone + gauge-tray water level (HiTide / Flood Watch)

Written 2026-11-08 for the next coding agent. Read this top to bottom before touching anything.
Owner: the user (Windows laptop `ayush_aw7x`). Hackathon: HackUTD 2026, submissions close Sun Nov 8, 12:00 PM CT.

---

## 0. TL;DR

- A DJI **Tello (original, non-EDU firmware)** streams video to a laptop. A Python **bridge/dashboard**
  (`backend/scripts/tello_dashboard.py` + `.html`, cyberpunk HUD at http://127.0.0.1:8765) does live video,
  keyboard flight, telemetry, diagnostics, and the **water gauge**.
- The **water gauge** (`backend/gauge/`) reads flood depth off a 3D-printed **gauge tray**
  (`data/gauge_tray_160/`: CAD heightmap + manifest). Logic mirrors the real system: **CAD gives ground
  heights (before), vision measures the water surface (now), depth = surface - ground, change = now - before.**
- The tray's **ArUco tags printed badly; the demo has NO tags**. Pose comes from (a) **4 clicked rim corners**
  (reliable), or (b) **automatic outline** using the placement rule **"FLOOD WATCH edge faces the drone"**
  (straight-on stand fit validated synthetically; see section 9).
- The user wants an **isolated, lightweight demo integrated in the drone dashboard** only. Build it with
  `python backend/scripts/make_drone_demo.py` -> `dist/drone-demo/` + `dist/drone-demo.zip` (149 KB). A copy is
  kept at `C:\Users\ayush_aw7x\OneDrive\Desktop\HiTide-drone-demo.zip`. Do not depend on the FastAPI backend
  or the React console for the demo.
- The Tello **cannot be propped nose-down**. Gauge setup = drone **level on a ~15 cm stand, ~43 cm back from the
  tray centre** (~20 deg down view), **motors off**. Flying = take off from a **flat floor** only.

---

## 1. Repo, branches, environment

- Repo: `C:\Users\ayush_aw7x\OneDrive\Documents\ChatGPT\Lifeguard`. Remote `origin` = `github.com/adityakothuri/hackUTD`
  (GitHub redirects to **adityakothuri/HiTide**; pushes work).
- **Current branch: `feat/gauge-water-level`** (latest `ff99db2`), cut from `feat/tello-drone`. Both pushed.
  No PR opened (user said "not yet" twice; don't open one unless asked).
- Teammate branches (not ours): `feat/safety-core` (Aditya: his own Tello mission `backend/drone/tello.py`,
  tabletop vision `backend/vision/*`, big), `feat/backend-sim`, `feat/live-observe`, `feat/frontend` (sid), `ScrabbleBot`.
  Our gauge code lives in `backend/gauge/` precisely to avoid clashing with Aditya's `backend/vision/`.
- Uncommitted noise you can ignore: `data/feeds_cache/*.json` (backend auto-refreshes them).
- **Python environments**
  - `~/tello-env` (`C:\Users\ayush_aw7x\tello-env`): Python 3.12 venv with djitellopy 2.5.0, opencv-python 5.0
    (has `cv2.aruco`), numpy 2.5, av, PIL, pytest. **All drone/gauge code runs here.**
  - `backend/.venv`: the FastAPI backend (uv-created; **`uv` is NOT on PATH**; use `.venv/Scripts/python.exe`).
    It has **no cv2**, so gauge tests `importorskip("cv2")` and skip there.
- Shell: Git Bash on Windows. Heredocs with backslashes mangle easily; write patch scripts to a file and run them
  (the scratchpad pattern used all session). `\n` inside `python - <<'EOF'` replacement strings has bitten us.

## 2. How to run

```bash
# Drone dashboard (bridge + HUD + gauge). Laptop must be on the TELLO-XXXXXX Wi-Fi for a real drone.
~/tello-env/Scripts/python.exe backend/scripts/tello_dashboard.py        # opens http://127.0.0.1:8765
# Standalone demo build (what the user will actually run)
~/tello-env/Scripts/python.exe backend/scripts/make_drone_demo.py        # dist/drone-demo + zip; run.bat inside
# Offline gauge image (no drone)
cd backend && ~/tello-env/Scripts/python.exe -m gauge.demo --level-ft 3.5 --out gauge.png
# Tests
cd backend && ~/tello-env/Scripts/python.exe -m pytest gauge/tests scripts/tests_gauge_bridge -q -p no:cacheprovider   # 115 pass, ~2.3 min
cd backend && .venv/Scripts/python.exe -m pytest -q                                                                  # 449 pass
cd frontend && npx tsc -b && npx vitest run                                                                          # 81 pass
```

Desktop launchers (user's machine, not in repo): `Tello dashboard.bat`, `Tello check`, `Tello stream`, `Tello fly`,
`Tello battery`, `Tello self-test`, `Tello diagnose`, `Flood Watch.bat` (backend + frontend + bridge, args: ports).

Logs and recordings: `C:\Users\ayush_aw7x\tello-test\` -> `dashboard.log`, `flight_*.csv` (1 row/s from takeoff
to landing), `battery_profile.json`, `report*.txt`, `diagnose.txt`.

## 3. Architecture

```
Tello --UDP 8889/8890/11111--> tello_dashboard.py (ThreadingHTTPServer 127.0.0.1:8765)
                                 |- Drone: connect, video (MJPEG), rc loop 20 Hz, watchdog/reconnect, safety
                                 |- GaugeService: thread ~2 Hz -> gauge.water.GaugeReader.update(frame)
                                 '- tello_dashboard.html (HUD): video, telemetry, flight, Water gauge card
(optional, not for the demo) FastAPI backend /api/live-drone/* forwards to the bridge; React console
  frontend/src/evidence/LiveDronePanel.tsx shows Live drone + Water gauge cards.
```

### 3.1 Bridge (`backend/scripts/tello_dashboard.py`) key facts
- Security (from a security review): `request_problem()` rejects foreign `Host` (DNS rebinding), foreign `Origin`,
  **non-JSON POSTs (415)** and cross-site GETs; body capped and must be a JSON object; max 4 video streams.
  **Every POST caller must send `Content-Type: application/json`** (HUD uses `JSON_HEADERS`). Tests:
  `backend/scripts/tests_gauge_bridge/test_bridge_security.py`.
- Takeover: a new dashboard POSTs `/shutdown` to an old one on the same port, which lands and exits. Port reuse is
  disabled (`DashboardServer.allow_reuse_address=False`) because Windows otherwise lets two copies share a port.
- Watchdog: no state packets for 2 s -> "link lost", re-sends `command`+`streamon` every 3 s.
- `flush_replies()`: original Tello firmware sometimes answers `command` twice; clears stray replies before
  takeoff/land so replies don't shift by one.
- **Land is never blocked** (separate `landing` flag; resends `land` until height 0).
- Safety still ON: auto-land when on the floor with motors running; descent/drift/wobble diagnostics;
  launch refused above **6 deg tilt** (`MAX_TILT_DEG`), hot (>= 80 C) blocks takeoff.
- **Battery restrictions OFF** (user request): `BATTERY_GUARD = env TELLO_BATTERY_GUARD == "1"` gates the 20 %
  floor, worn-battery takeoff margin, auto-land at lift-loss+4 %, gentle mode. Profile file still recorded.
- Routes: `GET /`, `/status`, `/video`, `/gauge/status`, `/gauge/overlay.jpg`;
  `POST /action/{takeoff|land|emergency}`, `/rc`, `/shutdown`, `/gauge/{baseline|start|stop|corners}`.
  `/gauge/corners` body `{"points": [[x,y]x4]}` (frame px) or `{"clear": true}`.
- Gauge facing: `GAUGE_TRAY_FACING` env, default `flood_watch`; `any` = let the terrain decide.
- Finds `gauge/` beside itself (demo layout) else `backend/` (repo layout).

### 3.2 Gauge pipeline (`backend/gauge/`)
- `model.py`: `load_tray()` (env `GAUGE_TRAY_DIR`, else repo `data/gauge_tray_160`, else `tray/` beside the
  package). **Convention: `height_mm[iy, ix]` at x = ix*res, y = iy*res (res 0.32 mm), z up.** Tray 160x160 mm,
  rim top 22.0 mm, rim 8 mm wide, terraces every 2 mm (= 1 ft), pool 4.0 mm = 0 ft. Car road 6.98, body top 8.98,
  roof 10.38; road deck 4.6; 10 houses with ground heights. FLOOD WATCH text is on the y = 0 rim, GUADALUPE RIVER
  on y = D.
- `camera.py`: `tello_default()` fx = fy ~683 (from the 82.6 deg diagonal FOV; 920 was wrong), 960x720.
- `pose.py`: ArUco (DICT_4X4_50) PnP; only used if >= 3 tags are seen (not in the demo).
- `rim.py`: **tag-free pose**. CAD edge points (height steps, top and foot of each step, plus outlines) ->
  chamfer score vs Canny distance transform -> coordinate descent over rvec, tvec, focal.
  - `solve_clicked_pose`: 4 clicks in order (0,0),(W,0),(W,D),(0,D) = "left end of FLOOD WATCH edge, then go round";
    accepts either direction round; picks rotation on the RAW PnP fit (snapping first lets wrong rotations
    half-fit), override only if another fits 15 % better.
  - `solve_rim_pose` auto: outline quads (edge-based + Otsu brightness masks) x rotations x windings x near-edge
    height (rim top or z = 0) -> PnP -> quick descent -> full descent on the best few. With `facing="flood_watch"`
    only poses in front of the y = 0 edge (+-60 deg) are kept and the orientation margin check is skipped.
  - `rim_problem()`: None, or why (not found / doesn't line up > 7 px / can't tell orientation).
  - `rim_alignment()`: chamfer on always-dry edges (rim lip, outline) to detect camera movement.
- `water.py` `GaugeReader(model, cam=None, dye="blue", facing=None)`:
  - Pose per frame: tags if >= 3, else rim/corners, **locked** while the camera is still (background thumbnail AND
    dry-rim alignment); re-solved when it moves (rate-limited 1/s).
  - Visible cells via z-buffer ray march; wetness = Lab change vs **dry baseline** (+ dye-hue prior); dye-only if no
    baseline (confidence capped 0.6). `set_baseline` refuses if >= 3 % of cells look dyed AND a waterline fits.
  - Level fit over terraces -> reported as the **1 ft step** (ft = k + 0.5, range (k, k+1)); exact-terrace pours
    are ambiguous by physics.
  - Withholds (None + reason) when: no pose, < 1500 visible cells, flat score, **view < 16 deg down**, or
    **confidence < 50 % of the mode's cap**. Policy: never a confidently wrong number.
  - `update()`: median of last 8, outlier/jump rejection, car-level hysteresis 0.3 mm.
  - Outputs: ft, ft_range, confidence, crossing_flooded, car_level (none/wheels/doors/windows/roof), houses_flooded,
    **depths** (per place: river channel, low-water crossing, stranded car, house 1..10 -> before_ft, now_ft,
    now_ft_range, change_ft, flooded), pose_source, baseline_moved, wet_fraction, focal_px, reason, ts.
  - Overlay: rim outline + "FLOOD WATCH edge"/"RIVER edge" labels (to catch misordered clicks), water shaded by depth.
- `synth.py`: independent renderer for tests (`draw_tags=False` for the tag-free tray).
- `demo.py`: CLI render + read + overlay PNG.

## 4. Demo build (`backend/scripts/make_drone_demo.py`)
Copies `tello_dashboard.py/.html`, `gauge/` (no tests), `tray/manifest.json + truth.npz` (no tag sheet), writes
`requirements.txt`, `run.bat` (uses `~/tello-env` if present, else creates `.venv` and pip installs, needs internet
once; sets `GAUGE_TRAY_DIR`), `README.md` (flying vs gauge setups). Rebuild after any source change and recopy the
zip to the Desktop. Verified from an isolated unzip with `python -I` and a fake drone (no repo imports).

## 5. Operating the demo (what the user does)
1. Flying: flat floor, pitch/roll ~0, bright light, patterned floor helps (VPS). Press L if it sinks.
2. Gauge: tray with **FLOOD WATCH edge facing the drone**; drone level on a ~15 cm stand ~43 cm from the tray centre
   (camera ~16 cm above the rim, ~20 deg down), motors off. Best automatic results are **25-30 deg off to the side**
   of that edge, not dead centre.
3. If "tray not found" / "view too shallow": **Set tray corners** (4 clicks) -> check overlay labels.
4. **Capture dry baseline** (dry tray!) -> **Start** -> pour blue-dyed water -> read ft + depth by place.

## 6. Verified results (synthetic, unless noted)
- With tags (old path): 100 % within 0.5 ft at mid-step levels, stand mode.
- No tags, clicked corners (+-4 px): 42/42 within 0.5 ft (tilted views); level camera ~20 deg: 31/32 correct, 1 withheld.
- No tags, auto outline + facing rule: 31/56 correct, 25 withheld, **0 wrong**. Fails mostly dead-centre (section 9).
- Browser end-to-end (fake drone through the real bridge, console and HUD): corners -> baseline -> 3.5/4.5 ft,
  depth table, overlay, stale marker, wet-baseline refusal all work.
- **Real drone**: connection, video (34 fps), telemetry, flight, recordings all work. **Gauge never verified on the
  physical print.** Last real gauge attempt (09:34) failed with "tray not found" even with corners: caused by the
  click-direction bug, fixed in `6dd0698`, not re-tested on hardware.

## 7. Hardware truths (from real logs)
- **Battery is worn**: ~27-42 %/min drain, **loses lift around 41 %** (level drop, motors still spinning; proven by
  `flight_20261108_063702.csv`). Fully charge; keep flights short. Battery guard is off now, so it can drop.
- **Overheats sitting on**: hit 80-86 C idle; Tello refuses takeoff at ~80 C. Turn it off between runs.
- Earlier: lopsided lift = props on wrong motors (fixed by user); "error" on takeoff = needed IMU calibration (done).
- Crazy drift run (09:25): took off tilted ~21 deg (likely from the stand) -> VPS confused. Now launch refused > 6 deg.
- Laptop loses internet on TELLO Wi-Fi; the user sometimes uses HackUTD Wi-Fi to talk to agents. USB tethering
  keeps both.

## 8. Other work in this branch (context, not for the demo)
- FastAPI relay `backend/api/live_drone.py` (+ tests `backend/tests/test_live_drone.py`), contract in
  `docs/api-contract.md` ("Live drone", "Gauge tray water level").
- React console `LiveDronePanel.tsx` (Live drone + Water gauge cards, corner picking, depth table).
- HiTide branding across the frontend (global palette in `frontend/src/styles/tokens.css`, logo
  `frontend/public/hitide-logo.png`, "HiTide / HACKUTD 2026"). 3 pre-existing stylelint errors in
  `TexasMonitor.module.css` are not ours.
- Docs: `docs/gauge-water-level-plan.md`, `docs/gauge-tray-setup.md`, `docs/tello-drone-handoff.md`.
- Old helper scripts: `tello_check/stream/fly/battery/selftest/diagnose.py`, `gauge_tag_sheet.py`.

## 9. Straight-on outline detection (updated)

The dashboard now tries a level-camera fit seeded from the stand dimensions. It checks the direction and
position of all four top rim edges and their alignment with the CAD terrain, then falls back to the original
outline solver if the fit is poor. The original 56-case sweep with PYTHONHASHSEED=0 returned 53 correct,
3 withheld and 0 wrong, including 35/35 correct on the level stand. With the camera 155 mm above the rim,
418 mm back and PYTHONHASHSEED=1, the sweep returned 52 correct, 4 withheld and 0 wrong. These are synthetic
results. Testing the physical print is the next step.

### Original diagnosis
Symptom: level camera straight in front of the FLOOD WATCH edge (side 0 / -10 / +15 deg) -> pose found but the
reader withholds ("view too shallow (11 deg down)") or no pose. Root cause (diagnosed): `_hypotheses()` assigns
the near-edge outline corners either z = rim top or z = 0; straight-on, the visible near silhouette is the front
wall (bottom edge z = 0 at the ends, rim top above it) and the chamfer prefers the wrong height, putting the
camera too low (11 deg vs true 20 deg) although camera position error looks small (~9 mm) on the wet frame; the
**baseline (dry) frame** solve is the one that is off, and it is locked. Ideas, in order:
1. Detect both the rim-top near edge and the bottom near edge (two parallel lines at the bottom of the quad) and
   use the upper one for the near corners at z = rim top; or fit a 6-vertex hexagon outline.
2. Score near-edge hypotheses with `rim_alignment` (dry edges only) instead of all edges; prefer the hypothesis whose
   implied view angle matches the image's vanishing geometry.
3. Use the expected setup geometry as a prior (camera height ~16 cm, distance ~43 cm) to reject implausible poses.
4. Run the solve on several dry frames and take the median pose before locking.
Validation harness: scratchpad `facing_sweep.py` pattern (level poses via `_level_pose` in `gauge/tests/test_rim.py`).
Acceptance: dead-centre level views read correctly, still 0 wrong.

## 10. Other open items
- First real-print test of the gauge (user will do it). Ask for `dashboard.log` lines with "Water gauge" and the
  reason text if it fails.
- Car-level hysteresis and exact-terrace ambiguity are physics-limited; fine.
- Hover-mode reading (drone flying) is not supported reliably; stand mode only.
- The console/back-end gauge path is optional; keep it green but don't spend demo time on it.

## 11. User preferences and working rules
- Wants things to work for the demo, fast, lightweight, isolated; asks for end-to-end verification; dislikes manual
  steps ("I don't want to grade it manually"). Be honest about what's verified vs not.
- Don't delete teammates' code; the demo is a separate build. Commit/push only on this branch; no PR unless asked.
- CLAUDE.md: TDD with pytest for core logic; keep files < 800 lines, functions < 50; contract-first for payloads;
  no secrets; update the vault (`vault/00 Home.md`) after phases.
- Some actions are blocked by the permission classifier: killing processes the user started (e.g. the old backend
  on :8000 from 10:43 PM and old Vite on :5173 still run; they predate the drone work). Our own test servers can be
  stopped (bridge via POST /shutdown with JSON header; others via taskkill of PIDs we started).
- Ports: real dashboard 8765; tests used 8799 (bridge), 8010 (backend), 5180 (Vite). A test dashboard on 8765 will
  take over (shut down) the user's running dashboard; warn them if you do that.


## Demo overlay repair
The Demo boxes feature had a JavaScript startup error. pollDemo() ran before let demoOn was
initialized, so tracking requests stopped even after a successful anchor. Startup now initializes
the toggle before polling. Anchor enables the boxes and the panel shows tracking/lost status.
The tracker processes each camera frame once so a frozen video becomes stale. Anchors save the
reference image and transform requests save homography, inliers and age in events.jsonl.
Verified in headless Edge through the real bridge and Anchor button with synthetic camera motion.
A 35 px horizontal / 20 px vertical video shift moved the car box by the same amount, with no
browser errors. All 40 bridge tests passed. The desktop extracted latest folder and ZIP are updated.
Physical movement still needs verification. Overlay coordinates and water-depth labels are preset
in DEMO_OVERLAY and anchoring preserves their initial alignment.
Image tracking proof used the recorded drone photo from 10:08 and four known geometric transformations with blur, brightness and JPEG degradation. All four cases passed a maximum 3 px error threshold. Worst measured error was 0.295 px across eight manually marked reference points. Frozen-frame age and blank-view hold behavior also passed. Visual proof and machine-readable results are in artifacts/overlay-proof. These tests use simulated motion applied to a real image. Live handheld 3D motion remains unverified.
Demo overlay controls now sit after the main dashboard, below the initial viewport. Independent water,
vehicle and label toggles persist across refreshes. Labels identify flood water and the vehicle.
The water polygon and labels follow the same tracked transformation as the car. Fixed SVG visibility
by toggling the actual hidden attribute. Browser test checked visible shapes, each toggle, persistence,
labels, and water motion from (300,430) to (335,450.1) after a known (35,20) image shift.
The demo panel top was 1532 px in a 900 px viewport. No browser errors. Desktop latest and ZIP updated.
Demo water shape and depths remain preset, and camera-motion tracking carries that outline with the view.
The preset overlay has been replaced in the dashboard by /analysis/status and live_overlay.py.
It segments blue/cyan dyed-water candidates on each new camera frame, returns contour rings with holes,
image coverage, timestamp and age, and logs the source frames and results. The browser draws these contours
and clears them on stale or missing video. All fixed depth labels and preset car boxes have been removed.
Depth still requires the calibrated GaugeReader. Colour segmentation can match other blue objects.
Vehicle box is disabled because this colour analysis does not locate vehicles. Controls remain below the fold.
43 bridge tests passed including water appearing, moving and disappearing with no anchor and frozen video aging.
Browser test detected a region at (300,200), then (335,220) after image shift, with no anchor or fixed depth labels
and no browser errors. Desktop extracted latest and ZIP updated.
Depth and geometry are now connected to /analysis/status. Gauge reading auto-starts at launch.
scene_geometry projects the CAD car body/roof footprint and tray rim through the current accepted pose.
A two-second pose refresh prevents slow movement retaining an old locked pose. The live panel renders
tray outline, car polygon, measured water-level range and measured local depth at the car. Missing or stale
measurements clear the geometry or show the actual gauge reason. All shapes and labels have visibility toggles.
Browser integration with synthetic camera images returned GAUGE TRAY, WATER LEVEL 3–4 FT, and
VEHICLE DEPTH 2.0 FT (roof). Car and tray geometry followed a changed camera viewpoint.
Security review found and fixed oversized POST truncation (now 413), invalid controls (400), cross-port
browser Origins (403), missing socket read timeout, and framing protection (DENY plus CSP frame-ancestors).
Browser checks verified the security responses and no JavaScript errors. Live desktop copy and ZIP updated.
Physical camera accuracy is still pending a connected drone test.
Frame-synchronous overlay update
The encoder now calls FrameOverlay.render on each video frame before JPEG encoding. Both the dashboard
and console receive the same annotated MJPEG. Water contours use half-resolution colour segmentation.
Vehicle and tray regions are aligned with user clicks and tracked between frames using local optical flow
plus a robust affine fit. The inaccurate CAD-projected overlay is no longer drawn on the live feed.
Vehicle labels contain no depth. Water regions contain no blue-dye label.
Bottom controls include visibility, Align vehicle (two opposite corners), Align tray (four rim corners),
and a manual demo depth field. That value is visibly labelled DEMO and varies smoothly within 0.03 ft.
The console's Kerrville live-drone panel contains the same controls and alignment workflow.
Backend relay routes added. Stopping the existing console backend was rejected by automatic approval,
so the Vite development proxy routes /api/live-drone/analysis directly to the local bridge using the
bridge's same-origin identity. Verified this console relay returns 200 and the depth input works.
A 60-frame real-image motion test measured median render time 7.17 ms, p95 11.08 ms and 2.24 px car
position error. This measures processing cost, not actual drone video FPS. 43 bridge tests, 33 relay
tests and 81 frontend tests pass. TypeScript compiles. Live drone frame availability is still required
for hardware tracking validation.
A new /drone console route and Drone navigation tab contain the shared LiveDronePanel only, including
live video, flight controls, telemetry, water gauge and bottom overlay/alignment/demo-depth controls.
It works independently of the Kerrville evidence state and omits road maps, source health and inspection
queues. Navigation added to Texas and Kerrville tabs. TypeScript builds, all 81 frontend tests pass,
and browser navigation from Texas to Drone passed with no JavaScript errors.
Demo depth standard deviation is now configurable in both interfaces (default 0.02 ft, 0 means steady).
Smooth Gaussian noise replaces the fixed sine fluctuation. A 600-sample check at sigma 0.12 measured
0.120 ft sample standard deviation. Physical depth display remains nonnegative, so values near zero
are clipped and have a smaller observed standard deviation. Large Drone page heading removed.
Console static-feed bug was a 404 from its old backend live-drone routes. Vite now proxies all
/api/live-drone routes directly to the same bridge as the Tello dashboard, with /gauge mapped to
/gauge/status. Raw bridge status is normalized by the console. Stale real video stays displayed with
a Video stale notice instead of switching to a cached sample. Verified status and gauge through console.
No aligned regions were present in the running renderer, and the drone link was disconnected with
video stale. Vehicle/tray alignment requires fresh video and user corner selection.
Visible depth label changed to WATER DEPTH at the user's request. The value remains user-entered
with configured Gaussian variation, so this label change does not make it a measured depth.
Browser proof for gauge presentation and automatic regions is saved in artifacts/overlay-proof/
console-gauge-and-boxes.png and console-blank-state.png. Tests use a simulated camera image through
the real GaugeService, FrameOverlay, bridge API and console React page with API routing to the test
bridge. Filling the UI depth field with 2.5 and stddev with 0 yielded Water gauge 2.50 ft. Valid gauge
pose seeded both car and tray regions; a blank frame cleared boxes and returned ft=null. The separate
video depth caption is removed. Blank/stale output suppresses the manual gauge value.
Automatic approval rejected restarting the live dashboard. Source and desktop package are updated,
but the old live process needs restarting before these changes are active.
