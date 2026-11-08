"""Precompute drone vision results so the live demo never runs a model.

Run: cd backend && uv run python -m scripts.run_vision_batch

Reads data/drone_samples/flood_*.jpg + labels.json, writes <stem>_annotated.jpg, <demo stem>_thermal.jpg
and results.json (consumed by vision/catalog.py).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.config import DATA_DIR
from vision.assess import VEHICLE_CLASSES, assess
from vision.detect import detect

log = logging.getLogger("vision_batch")

SAMPLES_DIR = DATA_DIR / "drone_samples"
LABELS_PATH = SAMPLES_DIR / "labels.json"
RESULTS_PATH = SAMPLES_DIR / "results.json"
URL_PREFIX = "/static/drone/"

PERSON_BGR = (0x37, 0x18, 0xE3)  # State Farm red #E31837
VEHICLE_BGR = (255, 255, 255)
TEXT_ON_PERSON = (255, 255, 255)
TEXT_ON_VEHICLE = (20, 20, 20)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _label_for(det: dict[str, Any], placement: str | None) -> str:
    name = det["cls"] if placement is None else placement.replace("_", " ").upper()
    return f"{name} {det['conf']:.2f}"


def _draw_box(img: np.ndarray, box: list[float], text: str, color: tuple, text_color: tuple) -> None:
    h, w = img.shape[:2]
    scale = max(0.4, w / 1600)
    thick = max(1, round(w / 500))
    x1, y1, x2, y2 = (int(round(v)) for v in box)
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thick + 1, cv2.LINE_AA)
    (tw, th), base = cv2.getTextSize(text, FONT, scale, thick)
    ty = y1 - th - base - 4 if y1 - th - base - 4 > 0 else min(y2 + 2, h - th - base - 4)
    tx = min(max(0, x1), max(0, w - tw - 6))
    cv2.rectangle(img, (tx, ty), (tx + tw + 6, ty + th + base + 4), color, cv2.FILLED)
    cv2.putText(img, text, (tx + 3, ty + th + 2), FONT, scale, text_color, thick, cv2.LINE_AA)


def annotate(src: Path, dst: Path, dets: list[dict[str, Any]], people: list[dict[str, Any]]) -> None:
    """Vehicles in white, people in red with their placement. Boats are skipped (unused, noisy on debris)."""
    img = cv2.imread(str(src))
    if img is None:
        raise ValueError(f"could not read {src}")
    for det in dets:
        if det["cls"] in VEHICLE_CLASSES:
            _draw_box(img, det["box"], _label_for(det, None), VEHICLE_BGR, TEXT_ON_VEHICLE)
    for person in people:  # drawn last so people sit on top of vehicle boxes
        det = {"cls": "person", "conf": person["conf"]}
        _draw_box(img, person["box"], _label_for(det, person["placement"]), PERSON_BGR, TEXT_ON_PERSON)
    cv2.imwrite(str(dst), img, [cv2.IMWRITE_JPEG_QUALITY, 90])


def thermal(src: Path, dst: Path) -> None:
    """Fake thermal look: grayscale -> INFERNO colormap, clearly stamped as simulated."""
    img = cv2.imread(str(src))
    if img is None:
        raise ValueError(f"could not read {src}")
    out = cv2.applyColorMap(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.COLORMAP_INFERNO)
    w = out.shape[1]
    scale, thick = max(0.5, w / 1400), max(1, round(w / 600))
    text = "SIMULATED THERMAL"
    (tw, th), base = cv2.getTextSize(text, FONT, scale, thick)
    cv2.rectangle(out, (8, 8), (8 + tw + 12, 8 + th + base + 12), (0, 0, 0), cv2.FILLED)
    cv2.putText(out, text, (14, 14 + th), FONT, scale, (255, 255, 255), thick, cv2.LINE_AA)
    cv2.imwrite(str(dst), out, [cv2.IMWRITE_JPEG_QUALITY, 90])


VEHICLE_PLACEMENTS = frozenset({"on_roof", "inside_unknown"})


def process(image: Path, water_level: str, vehicle_people_only: bool = False) -> dict[str, Any]:
    img = cv2.imread(str(image))
    if img is None:
        raise ValueError(f"could not read {image}")
    h, w = img.shape[:2]
    dets = detect(image)
    result = assess(dets, w, h, water_level)
    if vehicle_people_only:
        # Curated demo frame: keep only people on/in a vehicle. Bystanders on the far bank would otherwise
        # be read as "in_water" by the single-frame shore heuristic (see labels.json demo_people).
        result = {**result, "people": [p for p in result["people"] if p["placement"] in VEHICLE_PLACEMENTS]}
    annotated = image.with_name(f"{image.stem}_annotated.jpg")
    annotate(image, annotated, dets, result["people"])
    log.info("%s: %d vehicles, %d people %s", image.name, sum(d["cls"] in VEHICLE_CLASSES for d in dets),
             len(result["people"]), [p["placement"] for p in result["people"]])
    return {
        "image_url": URL_PREFIX + image.name,
        "annotated_url": URL_PREFIX + annotated.name,
        "car_detected": result["car_detected"],
        "water_level": result["water_level"],
        "water_level_source": result["water_level_source"],
        "people": result["people"],
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    labels = json.loads(LABELS_PATH.read_text())
    images: dict[str, dict[str, Any]] = {}
    for name, label in sorted(labels["images"].items()):
        path = SAMPLES_DIR / name
        if not path.is_file():
            log.warning("skipping %s: file missing", name)
            continue
        vehicle_only = name == labels["demo"] and labels.get("demo_people") == "vehicle_only"
        images[name] = process(path, label["water_level"], vehicle_only)

    demo = labels["demo"]
    if demo not in images:
        raise SystemExit(f"demo image {demo} was not processed")
    demo_path = SAMPLES_DIR / demo
    thermal(demo_path, demo_path.with_name(f"{demo_path.stem}_thermal.jpg"))

    RESULTS_PATH.write_text(json.dumps({"images": images, "demo_case": images[demo]}, indent=2) + "\n")
    log.info("wrote %s (%d images, demo=%s)", RESULTS_PATH, len(images), demo)


if __name__ == "__main__":
    main()
