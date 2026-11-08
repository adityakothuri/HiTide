"""Measure the water on the 3D-printed Kerrville tray and score it against the CAD ground truth.

    cd backend
    uv run python -m scripts.run_tabletop --source synth --rise 3,6,10,11
    uv run python -m scripts.run_tabletop --source images:../captures/pour3 --poured-ml 180
    uv run python -m scripts.run_tabletop --source video:../captures/pour3.mp4 --level-mm 9.62
    uv run python -m scripts.run_tabletop --source tello --poured-ml 180     # streams, never takes off

Truth for real frames: --poured-ml (pour table from the CAD) or --level-mm (caliper depth on the channel floor
plus the channel floor height in manifest.json). Results append to data/print_model/runs.jsonl.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from vision.camera import Intrinsics
from vision.tabletop import (
    MODEL_DIR, Reading, TabletopModel, default_camera, frames_with_pose, level_from_pour, load_model,
    measure_frames, synthetic_reading, true_reading,
)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
VIDEO_EVERY_N = 6
MAX_FRAMES = 30
TELLO_GRAB_S = 6.0
TELLO_EVERY_S = 0.2


def load_camera(path: str | None, width: int, height: int, hfov: float | None) -> tuple[Intrinsics, np.ndarray | None]:
    if not path:
        return default_camera(width, height, hfov), None
    c = json.loads(Path(path).read_text())
    cam = Intrinsics(c["fx"], c["fy"], c["cx"], c["cy"], int(c["width"]), int(c["height"]))
    return cam, (np.asarray(c["dist"], dtype=float) if c.get("dist") else None)


def read_images(folder: Path) -> list[np.ndarray]:
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXT)
    if not files:
        raise SystemExit(f"no images in {folder}")
    frames = [(p, cv2.imread(str(p))) for p in files[:MAX_FRAMES]]
    bad = [p.name for p, f in frames if f is None]
    if bad:
        raise SystemExit(f"unreadable images: {bad}")
    return [f for _, f in frames]


def read_video(path: Path) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    frames, k = [], 0
    while len(frames) < MAX_FRAMES:
        ok, f = cap.read()
        if not ok:
            break
        if k % VIDEO_EVERY_N == 0:
            frames.append(f)
        k += 1
    cap.release()
    if not frames:
        raise SystemExit(f"could not read frames from {path}")
    return frames


def read_tello() -> list[np.ndarray]:
    """Stream only: hold or mount the Tello over the tray (no take-off over open water)."""
    from djitellopy import Tello  # optional dependency

    tello = Tello()
    tello.connect()
    tello.streamon()
    try:
        reader, frames, last = tello.get_frame_read(), [], None
        end = time.monotonic() + TELLO_GRAB_S
        while time.monotonic() < end:
            f = reader.frame
            if f is not None and f is not last:                                  # skip repeats of a stale frame
                frames.append(np.ascontiguousarray(f[:, :, ::-1]))               # RGB -> BGR
                last = f
            time.sleep(TELLO_EVERY_S)
        return frames
    finally:
        tello.streamoff()


def grab(source: str) -> list[np.ndarray]:
    if source == "tello":
        return read_tello()
    kind, _, arg = source.partition(":")
    if kind == "images":
        return read_images(Path(arg))
    if kind == "video":
        return read_video(Path(arg))
    raise SystemExit(f"unknown source {source!r} (synth | images:<dir> | video:<file> | tello)")


def fmt(r: Reading, truth: Reading) -> str:
    if r.rise_m is None:
        return f"{r.station:8s} true rise {truth.rise_m:6.2f} m | no level ({'; '.join(r.reasons[:2]) or 'no edge'})"
    err = r.rise_m - truth.rise_m
    depth = "-" if r.depth_in is None else f"{r.depth_in:5.1f} in (true {truth.depth_in:5.1f})"
    return (f"{r.station:8s} true rise {truth.rise_m:6.2f} m | measured {r.rise_m:6.2f} m "
            f"[{r.rise_lo_m:.2f}, {r.rise_hi_m:.2f}] err {err:+.2f} m "
            f"({r.level_mm - truth.level_mm:+.2f} mm on the print) | depth {depth} | "
            f"{r.confidence}, {r.edge_points} edge pts, {r.sides} side(s)")


def log_run(rows: list[dict]) -> None:
    with (MODEL_DIR / "runs.jsonl").open("a") as fh:
        for row in rows:
            fh.write(json.dumps(row, default=float) + "\n")


def run_synth(model: TabletopModel, stations: list[str], rises: list[float], cam: Intrinsics) -> list[dict]:
    rows = []
    for row, rise in enumerate(rises):
        level = model.scale.level_mm(rise, model.zref_m)
        for sid in stations:
            truth = true_reading(model, sid, level, cam)
            r = synthetic_reading(model, sid, level, seed=row, cam=cam)   # fresh pose/mask noise per row
            print(fmt(r, truth))
            rows.append({"source": "synth", "measured": asdict(r), "truth": asdict(truth)})
    return rows


def run_real(model: TabletopModel, stations: list[str], frames: list[np.ndarray], level_mm: float,
             cam: Intrinsics, dist: np.ndarray | None, mirror: bool, source: str) -> list[dict]:
    h, w = frames[0].shape[:2]
    if (w, h) != (cam.width, cam.height):
        if abs(w * cam.height - h * cam.width) > max(w, h):   # a different aspect would make fx != fy
            raise SystemExit(f"frames are {w}x{h} but the camera is {cam.width}x{cam.height}: "
                             "pass --width/--height (or --camera) matching the frames")
        cam = cam.scaled(w, h)
    if dist is not None:
        k = np.array([[cam.fx, 0, cam.cx], [0, cam.fy, cam.cy], [0, 0, 1]])
        frames = [cv2.undistort(f, k, dist) for f in frames]
    posed = frames_with_pose(model, frames, cam, mirror)
    print(f"{len(posed)}/{len(frames)} frames with a fiducial pose")
    rows = []
    for sid in stations:
        truth = true_reading(model, sid, level_mm, cam)
        r = measure_frames(model, sid, posed[-5:], cam)
        print(fmt(r, truth))
        rows.append({"source": source, "measured": asdict(r), "truth": asdict(truth)})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Score the drone vision pipeline on the printed Kerrville tray")
    ap.add_argument("--source", default="synth")
    ap.add_argument("--station", action="append", help="station id (default: every station with a road)")
    ap.add_argument("--rise", default="3,6,10,11", help="synth: world rises in metres")
    ap.add_argument("--poured-ml", type=float, help="truth: millilitres poured into the empty tray")
    ap.add_argument("--level-mm", type=float, help="truth: water level above the print bed (mm)")
    ap.add_argument("--camera", help="calibration JSON {fx, fy, cx, cy, width, height, dist}")
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--hfov", type=float)
    ap.add_argument("--mirror", action="store_true", help="frames come through a 45 degree mirror clip")
    args = ap.parse_args()

    model = load_model()
    stations = args.station or [s.id for s in model.stations.values() if s.road is not None]
    cam, dist = load_camera(args.camera, args.width, args.height, args.hfov)
    if args.source == "synth":
        rows = run_synth(model, stations, [float(x) for x in args.rise.split(",")], cam)
    else:
        if args.level_mm is None and args.poured_ml is None:
            raise SystemExit("real frames need truth: --poured-ml or --level-mm")
        level = args.level_mm if args.level_mm is not None else level_from_pour(model, args.poured_ml)
        if not args.camera:
            print("WARNING: nominal intrinsics (no --camera calibration): treat the error as indicative only")
        rows = run_real(model, stations, grab(args.source), level, cam, dist, args.mirror, args.source)
    log_run(rows)


if __name__ == "__main__":
    main()
