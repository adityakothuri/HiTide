"""Annotated snapshot image: water tint, vehicle/person boxes, and a readout band (plan 9: overlay.py)."""

from __future__ import annotations

import cv2
import numpy as np

from vision.detect import Det
from vision.grid import Seg
from vision.snapshot import VisionSnapshot
from vision.synth import ADE

WATER_BGR = np.array([214, 140, 30], np.float32)       # blue tint
PALETTE = {ADE["sky"]: (235, 206, 180), ADE["grass"]: (80, 150, 90), ADE["road"]: (110, 110, 110),
           ADE["water"]: (150, 100, 40), ADE["tree"]: (40, 90, 40)}
PRIORITY_BGR = {"critical": (40, 40, 220), "high": (0, 140, 255), "medium": (0, 200, 230), "low": (200, 200, 200)}


def colorize(seg: Seg) -> np.ndarray:
    """A viewable image for synthetic frames (label map -> flat colours)."""
    out = np.full((*seg.labels.shape, 3), 128, np.uint8)
    for lab, bgr in PALETTE.items():
        out[seg.labels == lab] = bgr
    return out


def _readout(snap: VisionSnapshot) -> list[str]:
    depth = "depth n/a" if snap.est_depth_in is None else f"{snap.est_depth_in:.0f} in"
    if snap.depth_at_road_range_in:
        depth += f" [{snap.depth_at_road_range_in[0]:.0f}-{snap.depth_at_road_range_in[1]:.0f}]"
    wet = {True: "WATER ON ROAD", False: "road dry (not 'safe')", None: "road not visible"}[snap.water_on_road]
    rise = "" if snap.rise_rate_in_per_hr is None else f"  {snap.rise_rate_in_per_hr:+.0f} in/hr"
    return [f"{snap.point_id}  {wet}  {depth}  {snap.depth_band or ''}",
            f"{snap.depth_method}  conf {snap.confidence}  {snap.trend}{rise}",
            "; ".join(snap.confidence_reasons)[:110]]


def annotate(image: np.ndarray, seg: Seg, snap: VisionSnapshot, dets: list[Det] | None = None) -> np.ndarray:
    img = image.copy()
    water = seg.p_water >= 0.5
    if water.shape != img.shape[:2]:
        water = cv2.resize(water.astype(np.uint8), (img.shape[1], img.shape[0])) > 0
    img[water] = (0.55 * img[water] + 0.45 * WATER_BGR).astype(np.uint8)
    pri = {a.track_id: a.priority for a in reversed(snap.alerts) if a.track_id is not None}
    boxes = {}
    for v in snap.vehicles:
        boxes[v.track_id] = f"{v.type} {v.band or ''}"
    for p in snap.people:
        boxes[p.track_id] = f"person {p.situation.replace('_', ' ')}"
    h, w = img.shape[:2]
    scale = max(0.4, w / 1600)
    band_h = int(78 * scale / 0.5)
    img = cv2.copyMakeBorder(img, 0, band_h, 0, 0, cv2.BORDER_CONSTANT, value=(24, 24, 24))
    for i, line in enumerate(_readout(snap)):
        cv2.putText(img, line, (10, h + int((22 + 24 * i) * scale / 0.5)), cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (240, 240, 240), 1, cv2.LINE_AA)
    for d in dets or []:
        if d.track_id not in boxes:          # not confirmed (persistence) -> not drawn
            continue
        x1, y1, x2, y2 = (int(round(c)) for c in d.box)
        color = PRIORITY_BGR.get(pri.get(d.track_id, ""), (255, 255, 255))
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        cv2.putText(img, boxes[d.track_id], (x1, max(12, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, scale * 0.9, color, 1,
                    cv2.LINE_AA)
    return img
