"""Build the standalone drone + water-gauge demo: one folder (and a zip) that runs on its own.

    python backend/scripts/make_drone_demo.py            # writes dist/drone-demo/ and dist/drone-demo.zip

The demo is just the Tello dashboard (live video, flight controls, water gauge with depth by place),
the `gauge` package and the gauge tray's CAD data. No Flood Watch backend, console or other systems.
It is generated from the repo's sources, so re-run this after changing them.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "backend" / "scripts"
GAUGE = REPO / "backend" / "gauge"
TRAY = REPO / "data" / "gauge_tray_160"
DEFAULT_OUT = REPO / "dist" / "drone-demo"
TRAY_FILES = ("manifest.json", "truth.npz")  # no tag sheet: this demo uses clicked corners, not tags
REQUIREMENTS = "djitellopy>=2.5.0\nopencv-python>=4.8\nnumpy>=1.26\n"

RUN_BAT = r"""@echo off
rem HiTide drone demo: Tello live video, flight controls and the water gauge.
rem 1) Connect this laptop's Wi-Fi to TELLO-XXXXXX   2) Double-click this file.
cd /d "%~dp0"
set GAUGE_TRAY_DIR=%~dp0tray
set PY=%USERPROFILE%\tello-env\Scripts\python.exe
if not exist "%PY%" set PY=%~dp0.venv\Scripts\python.exe
if not exist "%PY%" (
  echo First run: setting up Python packages. This needs internet once.
  py -3 -m venv "%~dp0.venv" || python -m venv "%~dp0.venv"
  "%~dp0.venv\Scripts\python.exe" -m pip install -q -r "%~dp0requirements.txt"
  set PY=%~dp0.venv\Scripts\python.exe
)
"%PY%" tello_dashboard.py
pause
"""

README = """# HiTide drone demo (standalone)

Live Tello video, flight controls, and the water gauge that reads flood depth off the printed gauge tray
(no fiducial tags needed: you click the tray's 4 corners once).
Nothing else from Flood Watch is needed.

## Run
1. Turn the Tello on. Connect the laptop's Wi-Fi to **TELLO-XXXXXX** (the laptop loses internet; that's fine).
2. Double-click **run.bat**. The dashboard opens at http://127.0.0.1:8765 (first run on a new laptop
   installs the Python packages, which needs internet once).
3. Stop with **Ctrl+C** in the black window (it lands the drone first if flying).

## Flying vs reading the gauge: two different setups
- **To fly:** take off from a **flat, level floor** (not the stand, not a table edge, not your hand). Lifting off
  a raised box makes the downward sensor see the floor drop away, and the drone lurches and drifts. The
  dashboard shows "pitch/roll" at connect: both should be near 0 before you press Launch.
- **To read the gauge:** the stand below, **motors off**. Don't take off from the stand.

## Read the water level (stand mode, motors off)
1. **Place the Tello level, on a stand above the tray, motors off** (its camera can't tilt, so height does the
   work). Recipe: the drone on a box or book stack about **15 cm tall**, about **43 cm back from the tray's
   centre**, facing the tray. That puts the camera about 16 cm above the rim, looking about 20 deg down, with
   the whole tray in the lower half of the picture. Too low/far and the dashboard says "view too shallow:
   raise the drone" instead of guessing. (Nose-down propping also works if you can manage it.)
2. **Set tray corners** (required: this tray has no readable tags). Click the 4 top outer corners of the rim
   on the video, starting at the LEFT end of the FLOOD WATCH edge, then going round. Turn on
   **Show gauge overlay** and check the green outline traces the rim and the FLOOD WATCH / RIVER labels sit
   on those edges; if not, set the corners again. The camera must not move after this (stand mode); if it
   does, the gauge notices and re-fits, but set the corners again after a big move.
3. **Capture dry baseline** before pouring anything.
4. **Start**, then pour blue-dyed water. The card shows the flood level in ft and **depth by place**:
   the CAD gives each place's ground height (before), vision measures the water surface (now), and the
   change is the difference. The overlay shades water by depth.

## Files
- `tello_dashboard.py` / `.html`: the dashboard. `gauge/`: the vision code. `tray/`: the tray's CAD data
  (heightmap and manifest). The pose comes from your 4 corner clicks, not from tags.
- Logs: `%USERPROFILE%\\tello-test\\dashboard.log` and `flight_*.csv`.
- Offline test image without a drone: `python -m gauge.demo --level-ft 3.5 --out gauge.png`.
"""


def build(out: Path = DEFAULT_OUT) -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name in ("tello_dashboard.py", "tello_dashboard.html", "live_overlay.py"):
        shutil.copy2(SCRIPTS / name, out / name)
    shutil.copytree(GAUGE, out / "gauge", ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"))
    (out / "tray").mkdir()
    for name in TRAY_FILES:
        shutil.copy2(TRAY / name, out / "tray" / name)
    (out / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8")
    (out / "run.bat").write_text(RUN_BAT.replace("\n", "\r\n"), encoding="utf-8")
    (out / "README.md").write_text(README, encoding="utf-8")
    archive = shutil.make_archive(str(out), "zip", root_dir=out.parent, base_dir=out.name)
    return Path(archive)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    archive = build(parser.parse_args().out)
    print(f"Built {archive.with_suffix('')} and {archive}")


if __name__ == "__main__":
    main()
