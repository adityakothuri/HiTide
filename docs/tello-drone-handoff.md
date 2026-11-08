# Handoff: DJI Tello drone (live video, telemetry, control)

Standalone tools for the stage-3 "drone" piece of Flood Watch: stream a real DJI Tello's camera
to the laptop, monitor it, and fly it from a browser dashboard. Not yet wired into the FastAPI
app or the React ops dashboard.

## Picking this up

- **Branch:** `feat/tello-drone` (cut from `feat/frontend` at `2ecc09b`). Only drone files are on it.
- **Owner laptop state (ayush_aw7x):** venv at `C:\Users\ayush_aw7x\tello-env` (djitellopy 2.5.0,
  opencv-python, av 19). Test output in `C:\Users\ayush_aw7x\tello-test\` (`report_run1.txt`,
  `dashboard.log`). Double-click launchers on the Desktop: `Tello check`, `Tello stream`,
  `Tello fly`, `Tello battery`, `Tello dashboard`, `Tello self-test`. These are not in the repo;
  each one just runs `tello-env\Scripts\python.exe backend\scripts\<script>.py`.
- **Drone:** `TELLO-9AD44A`, original (non-EDU) firmware, battery 88% at last test.
- **Next immediate step:** run `Tello self-test` on the drone Wi-Fi, wait for `DONE`, then read
  `~/tello-test/report.txt` to confirm the video (fps + `snapshot_as_dashboard.jpg` colors).
  Then do one short take off / hover / land through the dashboard.
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
- **Video on the real drone is not yet confirmed.** The first self-test run stopped after `streamon`.
  Video startup now has a timeout in the self-test and runs in the background in the dashboard,
  so a stuck decoder can't block telemetry or controls.
- Dashboard verified end to end against a fake drone (video, status, take off/land).
- Flight through the dashboard has not been tested on the real drone yet.

## Known quirks

- The original Tello firmware answers `temp?` as `61~63C`, which crashes djitellopy's
  `query_temperature()`. The scripts send the raw `temp?` command instead.
- `sdk?` and `sn?` return "unknown command" on this firmware. That's expected.
- A solid red LED means the self-check failed: restart on a flat surface, let it cool, or run IMU
  calibration in the official Tello app. A blinking red LED means low battery.

## Next steps

- Confirm video and flight on the real drone.
- Move the drone into `backend/drone/`: an MJPEG endpoint plus status/control routes in FastAPI, a
  drone panel in the ops dashboard (`frontend/`), and a fallback to cached footage in `data/` when no
  Tello is connected. Add the payloads to `docs/api-contract.md` first.
