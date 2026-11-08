"""Live drone frames (Tello hover) -> VisionSnapshot. The bridge between the real drone and the vision model.

The Tello has no GPS and the indoor scene has no elevation map, so the water edge cannot be turned into a
water surface: depth stays null (depth only ever comes from water edge + elevation). What a hover does give:
- water on the road, voted over the whole hover (median water share of the frame), never "dry";
- vehicles and people, tracked by YOLO + ByteTrack and kept only after 5 frames (no one-frame ghosts);
- alerts (person on a car / in water, vehicle in water -> boat until depth is measured).

Indoors the "flood" is a blue sheet, which pretrained flood models don't call water, so the HSV colour
fallback is switched on for live frames (overview 9.4 demo fallback). Outdoors, set color_fallback=False.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from functools import lru_cache
from statistics import median
from typing import Any, Mapping

import numpy as np

from app.config import DATA_DIR
from vision.detect import Det
from vision.grid import Seg
from vision.pipeline import PHOTO_WET_FRAC, StepInput, snapshot_from_photo
from vision.snapshot import VisionSnapshot

log = logging.getLogger(__name__)
SNAP_DIR = DATA_DIR / "drone_samples" / "snapshots"
MAX_FRAMES = 30                 # bound the work per hover (SegFormer ~0.15 s/frame, CLIPSeg every 5th)
RECENT_FRAMES = 5               # objects: union of persisted tracks over the last N frames (one miss != gone)
SINGLE_FRAME_REASON = "single frame (no tracking)"
_models_lock = threading.Lock()  # SegFormer/YOLO tracker state are not safe to share across threads


def hover_snapshot(point_id: str, segs: Sequence[Seg], dets: list[Det], step: StepInput,
                   cfg: Mapping[str, Any]) -> VisionSnapshot:
    """Pure: fuse a hover's segmentations + the last frame's persisted detections into one snapshot."""
    if not segs:
        raise ValueError("a hover needs at least one frame")
    last = snapshot_from_photo(point_id, segs[-1], dets, step, cfg)
    cover = median(float((s.p_water >= 0.5).mean()) for s in segs)
    wet_vehicle = any(v.in_water for v in last.vehicles)
    wet = True if cover >= PHOTO_WET_FRAC or wet_vehicle else None   # tri-state: never claims dry
    reasons = [r for r in last.confidence_reasons if r != SINGLE_FRAME_REASON]
    reasons.insert(1, f"hover: {len(segs)} frames, water {100 * cover:.0f}% of frame (median)")
    if wet is None:
        reasons.append("no water seen: unknown, not dry (road extent unknown without a map)")
    return last.model_copy(update={"water_on_road": wet, "confidence_reasons": reasons[:20]})


def recent_tracks(per_frame: Sequence[list[Det]], n: int) -> list[Det]:
    """Persisted tracks seen in any of the last n frames, latest box per track id."""
    latest: dict[int, Det] = {}
    for dets in per_frame[-n:]:
        for d in dets:
            latest[d.track_id] = d
    return list(latest.values())


@lru_cache(maxsize=2)
def _segmenter(color_fallback: bool):
    from vision.segment import Segmenter

    return Segmenter(color_fallback=color_fallback)


def save_image(name: str, image_bgr: np.ndarray) -> str:
    """Write an annotated JPG under the static snapshots dir; returns its /static URL (safe filename)."""
    import cv2

    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)[:90] + ".jpg"
    if not cv2.imwrite(str(SNAP_DIR / safe), image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 88]):
        raise OSError(f"could not write {safe}")
    return f"/static/drone/snapshots/{safe}"


def run_hover(frames_bgr: Sequence[np.ndarray], point_id: str, drone_id: str, t: float,
              color_fallback: bool = True) -> VisionSnapshot:
    """Blocking (run in a worker thread): segment + track every frame, return the annotated snapshot."""
    from vision.config import vision_config
    from vision.detect import Tracker
    from vision.overlay import annotate

    frames = [f for f in frames_bgr if f is not None and f.ndim == 3 and f.size][-MAX_FRAMES:]
    if not frames:
        raise ValueError("no usable frames from the drone")
    cfg = vision_config()
    with _models_lock:
        seg_model = _segmenter(color_fallback)
        seg_model.reset()
        tracker = Tracker()
        segs, per_frame = [], []
        for frame in frames:
            per_frame.append(tracker.update(frame))
            segs.append(seg_model.run(frame))
    dets = recent_tracks(per_frame, RECENT_FRAMES)
    step = StepInput(t, drone_id=drone_id, source="live", simulated=False,
                     extra_reasons=("live drone: no GPS fix",))
    snap = hover_snapshot(point_id, segs, dets, step, cfg)
    stamp = snap.time.strftime("%H%M%S")
    url = save_image(f"{point_id}_{drone_id}_{stamp}", annotate(frames[-1], segs[-1], snap, dets))
    log.info("live hover %s: %d frames wet=%s people=%d", point_id, len(frames), snap.water_on_road, snap.people_seen)
    return snap.model_copy(update={"image_url": url})
