"""YOLO object detection for drone frames (offline only; the live demo reads precomputed results)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import DATA_DIR

MODEL_PATH = DATA_DIR / "models" / "yolov8n.pt"
MIN_CONF = 0.25
# Inference size: larger than the 640 default so small people on car roofs are found.
IMG_SIZE = 1280
# COCO ids we care about.
CLASSES = {0: "person", 2: "car", 5: "bus", 7: "truck", 8: "boat"}


@lru_cache(maxsize=1)
def _model():
    from ultralytics import YOLO  # heavy import, only when actually detecting

    if not MODEL_PATH.exists():
        # Ultralytics downloads into the CWD, so fetch into data/models/ explicitly.
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        from ultralytics.utils.downloads import attempt_download_asset

        attempt_download_asset(str(MODEL_PATH))
    return YOLO(str(MODEL_PATH))


def detect(image_path: str | Path) -> list[dict[str, Any]]:
    """Detections as [{cls, conf, box:[x1,y1,x2,y2]}] for person/car/bus/truck/boat with conf >= MIN_CONF."""
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    # agnostic_nms: one box per object, not a car box and a truck box on the same vehicle.
    result = _model().predict(
        str(path), conf=MIN_CONF, imgsz=IMG_SIZE, classes=list(CLASSES), agnostic_nms=True, verbose=False
    )[0]
    return [
        {
            "cls": CLASSES[int(c)],
            "conf": round(float(p), 3),
            "box": [round(float(v), 1) for v in xyxy],
        }
        for xyxy, p, c in zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist(), result.boxes.cls.tolist())
    ]


# ---------------------------------------------------------------------------------------------
# Live tracking (drone vision plan 7.1): ByteTrack IDs + a persistence filter so a one-frame hit
# from a reflection or debris can never raise an alert.
# ---------------------------------------------------------------------------------------------

from dataclasses import dataclass, field  # noqa: E402
from types import MappingProxyType  # noqa: E402
from typing import Mapping  # noqa: E402

import numpy as np  # noqa: E402


@dataclass(frozen=True)
class Det:
    track_id: int
    cls: str
    conf: float
    box: tuple[float, float, float, float]   # x1, y1, x2, y2 pixels


@dataclass(frozen=True)
class Persistence:
    """How many processed frames each track id has been seen in. Immutable: update() returns a new one."""
    counts: Mapping[int, int] = field(default_factory=lambda: MappingProxyType({}))
    min_frames: int = 5

    def update(self, dets: list[Det]) -> tuple["Persistence", list[Det]]:
        counts = dict(self.counts)
        for d in dets:
            counts[d.track_id] = counts.get(d.track_id, 0) + 1
        confirmed = [d for d in dets if counts[d.track_id] >= self.min_frames]
        return Persistence(MappingProxyType(counts), self.min_frames), confirmed


def reset_tracks() -> None:
    """Forget ByteTrack tracks from a previous stream (ultralytics keeps them on model.predictor)."""
    predictor = getattr(_model(), "predictor", None)
    for tracker in getattr(predictor, "trackers", None) or []:
        tracker.reset()


class Tracker:
    """YOLOv8n + ByteTrack over a frame stream. update(frame) -> detections that have persisted."""

    def __init__(self, min_frames: int | None = None) -> None:
        from vision.config import vision_config

        cfg = vision_config()["detect"]
        self.conf = float(cfg["conf"])
        self.img_size = int(cfg["img_size"])
        self.classes = {int(k): v for k, v in cfg["classes"].items()}
        self.persistence = Persistence(min_frames=int(cfg["persist_frames"] if min_frames is None else min_frames))
        reset_tracks()   # ByteTrack state lives on the shared YOLO model: a new stream starts clean


    def raw(self, frame_bgr: np.ndarray) -> list[Det]:
        result = _model().track(
            frame_bgr, persist=True, tracker="bytetrack.yaml", conf=self.conf, imgsz=self.img_size,
            classes=list(self.classes), agnostic_nms=True, verbose=False,
        )[0]
        boxes = result.boxes
        if boxes is None or boxes.id is None:
            return []
        return [
            Det(int(i), self.classes[int(c)], round(float(p), 3), tuple(round(float(v), 1) for v in xyxy))
            for xyxy, p, c, i in zip(boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist(), boxes.id.tolist())
        ]

    def update(self, frame_bgr: np.ndarray) -> list[Det]:
        self.persistence, confirmed = self.persistence.update(self.raw(frame_bgr))
        return confirmed


def detect_still(image_path: str | Path) -> list[Det]:
    """Single photo (no tracking possible): ids are per-image indexes; callers must say 'single frame'.

    Uses the repo's tuned still-image threshold (MIN_CONF 0.25): the spec's 0.35 assumes the 5-frame
    persistence filter, which a single photo can't have.
    """
    from vision.config import vision_config

    cfg = vision_config()["detect"]
    classes = {int(k): v for k, v in cfg["classes"].items()}
    result = _model().predict(str(image_path), conf=MIN_CONF, imgsz=IMG_SIZE, classes=list(classes),
                              agnostic_nms=True, verbose=False)[0]
    return [
        Det(k, classes[int(c)], round(float(p), 3), tuple(round(float(v), 1) for v in xyxy))
        for k, (xyxy, p, c) in enumerate(zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist(),
                                             result.boxes.cls.tolist()))
    ]
