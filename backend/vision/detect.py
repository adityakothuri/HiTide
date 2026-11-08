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
