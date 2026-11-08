"""Run the drone vision pipeline and (optionally) POST snapshots to the backend.

  uv run python -m vision.run_pipeline --source synth:cp-0014 --at 2025-07-04T10:45:00Z --post
  uv run python -m vision.run_pipeline --source images:../data/drone_samples --post
  uv run python -m vision.run_pipeline --source video:clip.mp4 --point photo-clip

synth:<cp-id>  synthetic hover at a real critical point, flooded to the July 2025 replay truth (pose known)
images:<dir>   real photos, no pose: segmentation + YOLO only (no depth: depth needs pose + elevation)
video:<file>   real video, no pose: tracked detections, one snapshot every --every frames
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from app.config import DATA_DIR
from vision.config import vision_config
from vision.overlay import annotate, colorize
from vision.snapshot import VisionSnapshot

log = logging.getLogger("vision.run_pipeline")
API = os.environ.get("HITIDE_API", "http://127.0.0.1:8000")


def _save(name: str, image: np.ndarray) -> str:
    from vision.live import save_image

    return save_image(name, image)


def _post(snap: VisionSnapshot) -> None:
    import httpx

    r = httpx.post(f"{API}/api/snapshots", content=snap.model_dump_json(), timeout=30,
                   headers={"content-type": "application/json",
                            **({"x-vision-token": os.environ["VISION_INGEST_TOKEN"]}
                               if os.environ.get("VISION_INGEST_TOKEN") else {})})
    if r.status_code != 202:
        log.error("POST failed %s: %s", r.status_code, r.text[:300])
        return
    log.info("posted %s -> %s", snap.point_id, r.json())


def _emit(snap: VisionSnapshot, post: bool) -> None:
    print(snap.model_dump_json(indent=2))
    if post:
        _post(snap)


def run_synth(point_id: str, at: str, frames: int, post: bool) -> None:
    from sim.region import load_region
    from sim.region_flood import RegionFlood
    from vision.edges import RoadGeom
    from vision.measure import PointContext
    from vision.pipeline import GeoOrigin, PointState, StepInput, snapshot_from_hover
    from vision.scenes import anchored_scene, point
    from vision.segment import lut_from_names
    from vision.spread import spread
    from vision.synth import Noise, default_camera, make_frame, oblique_pose, render
    from vision.water_level import WLParams

    cfg = vision_config()
    region = load_region()
    flood = RegionFlood(region)
    pts = {p["id"]: p for p in json.loads((DATA_DIR / "region" / "hill_country" / "nodes.json").read_text())["points"]}
    t0 = datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp()
    a = anchored_scene(region, flood, point(pts, point_id), t0)
    cam = default_camera(640, 480)
    pose = oblique_pose(a.scene)
    rendered = render(a.scene, cam, pose)
    ctx = PointContext(point_id, a.scene.grid, RoadGeom(a.scene.road, 4.0), cam, lut_from_names())
    params = WLParams.from_config(cfg["water_level"])
    base = pose.perturbed(np.random.default_rng(7), 1.0, 0.5, 0.5)
    exclude = frozenset(point(pts, point_id)["edge_ids"])

    def spread_fn(lon: float, lat: float, wse: float) -> list[str]:
        return [s.edge_id for s in spread(region, lon, lat, wse, exclude=exclude)]

    state, snap, seg = PointState(), None, None
    for k in range(frames):
        f = make_frame(a.scene, cam, pose, Noise(flicker_frac=0.02, pose_sigma_m=0.2, pose_sigma_deg=0.1),
                       seed=k, rendered=rendered, est_base=base)
        seg = f.seg
        step = StepInput(t0 + 0.3 * k, drone_id="drone-vision", source="synthetic", simulated=True,
                         extra_reasons=(f"replay truth {a.truth_depth_in:.0f} in",))
        snap, state = snapshot_from_hover(ctx, GeoOrigin(a.lon, a.lat), state, seg, f.est_pose, [], step, params,
                                          cfg, spread_fn)
    url = _save(f"{point_id}_{at[11:16].replace(':', '')}", annotate(colorize(seg), seg, snap))
    _emit(snap.model_copy(update={"image_url": url}), post)


def run_images(folder: Path, post: bool) -> None:
    from vision.detect import detect_still
    from vision.pipeline import StepInput, snapshot_from_photo
    from vision.segment import Segmenter

    cfg = vision_config()
    seg_model = Segmenter()
    seg_model._zs_every = 1  # every photo is a new scene
    for path in sorted(folder.glob("flood_0[0-9].jpg")):
        img = cv2.imread(str(path))
        if img is None:
            log.warning("unreadable image %s", path)
            continue
        seg = seg_model.run(img)
        dets = detect_still(path)
        snap = snapshot_from_photo(f"photo-{path.stem}", seg, dets,
                                   StepInput(datetime.now(timezone.utc).timestamp(), source="photo", simulated=False),
                                   cfg)
        url = _save(f"photo-{path.stem}", annotate(img, seg, snap, dets))
        _emit(snap.model_copy(update={"image_url": url}), post)


def run_video(path: Path, point_id: str, every: int, post: bool) -> None:
    from vision.detect import Tracker
    from vision.pipeline import StepInput, snapshot_from_photo
    from vision.segment import Segmenter

    cfg = vision_config()
    seg_model, tracker = Segmenter(), Tracker()
    cap = cv2.VideoCapture(str(path))
    k = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        k += 1
        dets = tracker.update(frame)
        if k % every:
            continue
        seg = seg_model.run(frame)
        step = StepInput(datetime.now(timezone.utc).timestamp(), source="video", simulated=False,
                         extra_reasons=("video: no drone pose",))
        snap = snapshot_from_photo(point_id, seg, dets, step, cfg).model_copy(update={"source": "video"})
        url = _save(f"{point_id}_{k:05d}", annotate(frame, seg, snap, dets))
        _emit(snap.model_copy(update={"image_url": url}), post)
    cap.release()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="synth:<cp-id> | images:<dir> | video:<file>")
    ap.add_argument("--at", default="2025-07-04T10:45:00Z", help="replay time for synth (UTC)")
    ap.add_argument("--frames", type=int, default=8)
    ap.add_argument("--point", default="video-1")
    ap.add_argument("--every", type=int, default=15)
    ap.add_argument("--post", action="store_true", help=f"POST each snapshot to {API}/api/snapshots")
    args = ap.parse_args(argv)
    kind, _, arg = args.source.partition(":")
    if kind == "synth":
        run_synth(arg, args.at, args.frames, args.post)
    elif kind == "images":
        run_images(Path(arg), args.post)
    elif kind == "video":
        run_video(Path(arg), args.point, args.every, args.post)
    else:
        ap.error("source must be synth:, images: or video:")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
