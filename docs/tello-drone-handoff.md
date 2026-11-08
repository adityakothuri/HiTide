# Handoff: DJI Tello drone (live video, telemetry, control)

Standalone tools for the stage-3 "drone" piece of HiTide: stream a real DJI Tello's camera
to the laptop, monitor it, and fly it from a browser dashboard. Not yet wired into the FastAPI
app or the React ops dashboard.

## Picking this up

- **Branch:** built on `feat/tello-drone`; merged to `main` 2026-11-08.
- **Owner laptop state:** venv at `%USERPROFILE%\tello-env` (djitellopy 2.5.0,
  opencv-python, av 19). Test output in `%USERPROFILE%\tello-test\` (`report_run1.txt`,
  `dashboard.log`). Double-click launchers on the Desktop: `Tello check`, `Tello stream`,
  `Tello fly`, `Tello battery`, `Tello dashboard`, `Tello self-test`. These are not in the repo;
  each one just runs `tello-env\Scripts\python.exe backend\scripts\<script>.py`.
- **Drone:** `TELLO-9AD44A`, original (non-EDU) firmware, battery 88% at last test.
- **Next immediate step:** one short take off / hover / land through the dashboard on the real
  drone, and check the video colors in normal light. The self-test passed (0 failures); see Status.
- **Gotcha:** switching to the Tello Wi-Fi cuts the laptop's internet, which also cuts the Claude
  session. Use USB tethering from a phone to stay online, or rely on the self-test's saved report.

## Setup (once, while online)

The tools run in their own venv, separate from the backend's uv environment:

```bash
python3.12 -m venv ~/tello-env
~/tello-env/Scripts/python.exe -m pip install djitellopy opencv-python
```

Then connect the laptop Wi-Fi to the drone (`TELLO-XXXXXX`, no password). The laptop loses
internet while connected; everything below works offline. Allow Python through Windows Firewall
on Private **and** Public networks (UDP 8889 commands, 8890 state, 11111 video).

## Tools (`backend/scripts/`)

| Script | What it does |
|---|---|
| `tello_dashboard.py` + `.html` | **Main tool.** Browser dashboard at http://127.0.0.1:8765: live video, battery, height, temperature, flight time, take off/land/emergency, keyboard + hold-to-move controls, event log. Ctrl+C in the console lands first. |
| `tello_selftest.py` | Unattended no-flight test against the real drone. Writes `~/tello-test/report.txt` plus video snapshots. Use it when you can't stay online while on the Tello Wi-Fi. |
| `tello_check.py` / `.bat` | One-shot health check: does the drone answer, battery, temperature, attitude, Wi-Fi SNR. |
| `tello_battery.py` | Live battery + temperature monitor (every 5 s). |
| `tello_stream.py` / `.bat` | Video-only window. |
| `tello_fly.py` | Keyboard flight in an OpenCV window (older; the dashboard supersedes it). |
| `TELLO_STEPS.txt` | Step-by-step offline guide plus troubleshooting. |

Run any of them with `~/tello-env/Scripts/python.exe backend/scripts/<script>.py`. Only one tool
can talk to the drone at a time.

Dashboard keys: `T` take off, `L` land, `WASD` move, arrows climb/descend/turn, `Backspace`
emergency motor stop. Deadman: if the page loses focus or stops sending for 0.6 s, the drone hovers.
The server binds to 127.0.0.1 only and logs to `~/tello-test/dashboard.log`.

## Status (2026-11-08)

- Tested on the real drone (TELLO-9AD44A, original Tello firmware): commands, battery, Wi-Fi SNR,
  attitude, and state packets all pass.
- **Self-test run 2 on the real drone: 0 failures.** Video at 34 fps (first frame after 0.1 s),
  960x720; dashboard served 29 fps over HTTP with live status (battery 89%, 66 C).
- Video colors are not yet judged: the test snapshot was taken in a near-dark room.
- Dashboard take off/land verified against a fake drone.
- **Flight attempt 1 (03:34): the drone refused takeoff and land with a bare `error`, so no control
  was possible** (movement is only sent while flying). The laptop side worked: connected at 82%,
  video started. Suspects: IMU calibration needed (the drone showed a solid red LED earlier), heat
  after sitting powered on, a dark room, or an uneven surface. The dashboard now runs a preflight
  check (battery, temperature, tilt), sends one raw `takeoff` instead of 4 silent retries, and logs
  the exact reply plus battery/temperature/tilt/floor-sensor readings on refusal.
- The dashboard now refuses to start if another copy is already running. Windows otherwise let two
  copies share port 8765, and one was left running after the flight attempt.

## Known quirks

- The original Tello firmware answers `temp?` as `61~63C`, which crashes djitellopy's
  `query_temperature()`. The scripts send the raw `temp?` command instead.
- `sdk?` and `sn?` return "unknown command" on this firmware. That's expected.
- The firmware sometimes answers `command` twice. djitellopy then pairs every later reply with the
  wrong command (run 2 showed battery as `ok` and attitude as `63~65C`). `flush_replies()` in
  `tello_dashboard.py` clears stray replies after connecting and before take off/land. Land is also
  always enabled in the dashboard, so a wrong "flying" flag can never block landing.
- A solid red LED means the self-check failed: restart on a flat surface, let it cool, or run IMU
  calibration in the official Tello app. A blinking red LED means low battery.

## Wired into HiTide (2026-11-08)

The real drone now shows up in the ops console (`/console`, "Live drone" panel under the road map).

```
browser /console --(Vite proxy)--> backend :8000 /api/live-drone/* --(httpx)--> Tello bridge :8765 --(UDP)--> drone
```

- **Backend:** `backend/api/live_drone.py` forwards status, MJPEG video, take off/land/emergency and
  rc to the bridge (`TELLO_BRIDGE_URL`, default `http://127.0.0.1:8765`). No new backend dependencies;
  the bridge keeps its own venv and owns the drone's UDP ports. POSTs use the trusted-origin guard.
  Tests: `backend/tests/test_live_drone.py`. Contract: `docs/api-contract.md`, "Live drone".
- **Frontend:** `frontend/src/evidence/LiveDronePanel.tsx`, mounted in `Operations.tsx` (2 lines).
  It shows a LIVE badge with video and telemetry when the drone is connected, and otherwise a cached
  `/static/drone/flood_03.jpg` labelled "CACHED · NOT LIVE". Land is never disabled, including during
  takeoff. Keyboard flight stays on the bridge page (linked from the panel).
- **To demo live:** start the backend and frontend as usual, double-click `Tello dashboard` (the bridge),
  then connect the laptop to the TELLO Wi-Fi. Everything is on `localhost`, so losing internet on the
  drone Wi-Fi does not affect the demo. Use USB tethering from a phone if internet is also needed.
- Verified end to end with a fake-drone bridge (live video through the backend, takeoff/land, offline
  fallback). **Not yet verified with the real drone through the console.**

## Next steps

- Fly the real drone from the console once, with lights on over a patterned floor.
- Optional: link a live-drone snapshot to the stage-3 case (`vision.image_url`) instead of the
  sample image when the bridge is online.

## Worn battery protection (2026-11-08)

The current battery loses lift around 41% (level drop to the floor at ~27%/min drain; see
`~/tello-test/flight_20261108_063702.csv`). `~/tello-test/battery_profile.json` stores that level, and the
dashboard then: lands automatically 4% above it, refuses takeoff with under 60 s of margin, shows a
`LIFT Ns` countdown on the video HUD, and caps control inputs at 30 with a slower ramp. A new lift-loss
event updates the file. **Delete the file after swapping in a new battery.**

## Gauge tray water level (2026-11-08)

Branch `feat/gauge-water-level`. The camera reads flood depth off the printed gauge tray
(`data/gauge_tray_160/`): four ArUco tags give the camera pose, the CAD heightmap says which known-height
terraces should be wet, and the dry-vs-wet comparison picks the 1 ft step the water is in.

- Plan: `docs/gauge-water-level-plan.md`. Demo-day guide: `docs/gauge-tray-setup.md`. Tag sheet:
  `data/gauge_tray_160/tag_sheet.png` (print at 100%, check the 50 mm bar).
- Code: `backend/gauge/` (runs in `~/tello-env`; tests: `cd backend && ~/tello-env/Scripts/python.exe -m pytest gauge/tests scripts/tests_gauge_bridge -q -p no:cacheprovider`).
  Bridge `GaugeService` + HUD card; backend `/api/live-drone/gauge*`; console "Water gauge" card.
- Offline demo image: `cd backend && ~/tello-env/Scripts/python.exe -m gauge.demo --level-ft 3.5 --out gauge.png`.
- Use **stand mode**: Tello propped nose-down about 45 deg, motors off, 300-350 mm away. Hover at 20-25 deg
  can't read the tags and returns no reading (never a wrong one).
- Verified: synthetic sweep 100% within 0.5 ft at mid-step levels; console end to end in the browser
  (baseline, then 3.5 ft, roof, crossing flooded, 9/10 houses; stale marker; wet-baseline refusal).
  **Not yet run on the physical print.**
- Security (found in review): the bridge now refuses foreign Host/Origin, non-JSON POSTs and cross-site
  GETs, so a web page in the demo browser can't fly the drone.
