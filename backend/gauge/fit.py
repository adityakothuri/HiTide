"""Estimator internals: cell drape, visibility, wetness and the 1-D waterline fit.

The renderer in ``synth.py`` deliberately shares none of this code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

from .camera import Intrinsics, Pose, project
from .model import TrayModel

logger = logging.getLogger(__name__)

TARGET_STRIDE_MM = 1.0
EXCLUDE_BELOW_RIM_MM = 0.5     # cells this close to rim height are pads / rim / lettering
VIS_STEP_MM = 1.0
VIS_TOLERANCE_MM = 0.15
VIS_START_MM = 0.4
STEEP_SLOPE, STEEP_WEIGHT = 0.35, 0.3
IMAGE_MARGIN_PX = 2.0
LAB_SIGMA_PX = 1.0
CHANGE_L_WEIGHT = 0.25         # brightness changes (glare, exposure) count less than colour changes
CHANGE_LOW, CHANGE_HIGH = 6.0, 16.0
CHROMA_MIN = 3.0
HUE_BASE_WEIGHT = 0.6
DYE_LOW, DYE_HIGH = 5.0, 15.0
DYE_REF_PERCENTILE = 1.0
LEVEL_STEP_MM = 0.25
NEAR_BETA, NEAR_SIGMA_MM = 1.0, 3.0
RANGE_MARGIN = 0.012
DYE_DIRECTIONS = {"blue": (-0.2, -1.0), "green": (-1.0, 0.4), "red": (1.0, 0.3)}


@dataclass(frozen=True, eq=False)
class CellGrid:
    """Sub-sampled heightfield cells that are eligible for the drape."""

    points_mm: np.ndarray   # (N, 3) at ground height
    height_mm: np.ndarray   # (N,)
    quality: np.ndarray     # (N,) 1 on flat ground, lower on steep walls


@dataclass(frozen=True)
class LevelFit:
    level_lo_mm: float
    level_hi_mm: float
    agreement: float        # weighted agreement at the best level, 0-1
    contrast: float         # best minus worst agreement over the sweep


def dye_direction(dye: str) -> tuple[float, float]:
    """Unit (a*, b*) direction of the dye colour shift."""
    try:
        a, b = DYE_DIRECTIONS[dye.lower()]
    except (KeyError, AttributeError) as exc:
        raise ValueError(f"unknown dye {dye!r}; expected one of {sorted(DYE_DIRECTIONS)}") from exc
    norm = float(np.hypot(a, b))
    return a / norm, b / norm


def build_cell_grid(model: TrayModel) -> CellGrid:
    stride = max(1, int(round(TARGET_STRIDE_MM / model.res_mm)))
    hf = model.height_mm
    gy, gx = np.gradient(hf.astype(np.float64), model.res_mm)
    slope = np.hypot(gx, gy)[::stride, ::stride]
    sub = hf[::stride, ::stride].astype(np.float64)
    iy, ix = np.mgrid[0:hf.shape[0]:stride, 0:hf.shape[1]:stride]
    keep = sub < model.rim_top_mm - EXCLUDE_BELOW_RIM_MM
    points = np.stack([ix[keep] * model.res_mm, iy[keep] * model.res_mm, sub[keep]], axis=1)
    quality = np.where(slope[keep] > STEEP_SLOPE, STEEP_WEIGHT, 1.0)
    return CellGrid(points, sub[keep], quality)


def visible_mask(grid: CellGrid, model: TrayModel, camera_mm: np.ndarray) -> np.ndarray:
    """True where a straight line from the cell to the camera clears the heightfield."""
    hf, res = model.height_mm, model.res_mm
    ny, nx = hf.shape
    z_max = float(hf.max())
    start = grid.points_mm
    delta = np.asarray(camera_mm, dtype=np.float64)[None, :] - start
    dist = np.linalg.norm(delta, axis=1)
    unit = delta / np.maximum(dist, 1e-9)[:, None]
    visible = np.ones(len(start), dtype=bool)
    active = np.arange(len(start))
    step = VIS_START_MM
    while active.size:
        p = start[active] + step * unit[active]
        ix = np.clip(np.rint(p[:, 0] / res), 0, nx - 1).astype(np.int64)
        iy = np.clip(np.rint(p[:, 1] / res), 0, ny - 1).astype(np.int64)
        blocked = p[:, 2] < hf[iy, ix] - VIS_TOLERANCE_MM
        visible[active[blocked]] = False
        inside = (p[:, 0] >= 0) & (p[:, 1] >= 0) & (p[:, 0] <= (nx - 1) * res) & (p[:, 1] <= (ny - 1) * res)
        keep = ~blocked & inside & (p[:, 2] <= z_max) & (step < dist[active])
        active = active[keep]
        step += VIS_STEP_MM
    return visible


def project_cells(grid: CellGrid, cam: Intrinsics, pose: Pose, shape: tuple[int, int]
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Pixels (N,2) of every cell and a mask of those inside the frame."""
    px, depth = project(grid.points_mm, cam, pose)
    h, w = shape
    inside = (np.isfinite(px).all(axis=1) & (depth > 0) & (px[:, 0] >= IMAGE_MARGIN_PX)
              & (px[:, 1] >= IMAGE_MARGIN_PX) & (px[:, 0] <= w - 1 - IMAGE_MARGIN_PX)
              & (px[:, 1] <= h - 1 - IMAGE_MARGIN_PX))
    return px, inside


def to_lab(frame_bgr: np.ndarray) -> np.ndarray:
    """Lightly blurred CIE Lab image (float32, L 0-100)."""
    blurred = cv2.GaussianBlur(frame_bgr, (0, 0), LAB_SIGMA_PX)
    return cv2.cvtColor(blurred.astype(np.float32) / 255.0, cv2.COLOR_BGR2Lab)


def sample_lab(lab: np.ndarray, px: np.ndarray) -> np.ndarray:
    """Bilinear Lab samples (N,3); NaN pixels give NaN."""
    safe = np.nan_to_num(px, nan=0.0).astype(np.float32)
    out = cv2.remap(lab, safe[:, 0].reshape(1, -1), safe[:, 1].reshape(1, -1), cv2.INTER_LINEAR)
    return out.reshape(-1, 3)


def wetness_from_baseline(lab: np.ndarray, base_lab: np.ndarray, direction: tuple[float, float]) -> np.ndarray:
    """Wetness 0-1 from Lab change against the dry drape, nudged by agreement with the dye hue."""
    d = lab - base_lab
    mag = np.sqrt((CHANGE_L_WEIGHT * d[:, 0]) ** 2 + d[:, 1] ** 2 + d[:, 2] ** 2)
    change = np.clip((mag - CHANGE_LOW) / (CHANGE_HIGH - CHANGE_LOW), 0.0, 1.0)
    chroma = np.hypot(d[:, 1], d[:, 2])
    align = (d[:, 1] * direction[0] + d[:, 2] * direction[1]) / np.maximum(chroma, 1e-6)
    hue = np.where(chroma > CHROMA_MIN, HUE_BASE_WEIGHT + (1.0 - HUE_BASE_WEIGHT) * np.clip(align, 0.0, 1.0),
                   HUE_BASE_WEIGHT)
    return change * hue


def wetness_from_dye(lab: np.ndarray, direction: tuple[float, float]) -> np.ndarray:
    """Wetness 0-1 from the dye hue alone, relative to the least dye-coloured cells of this frame."""
    score = lab[:, 1] * direction[0] + lab[:, 2] * direction[1]
    reference = np.percentile(score, DYE_REF_PERCENTILE)
    return np.clip((score - reference - DYE_LOW) / (DYE_HIGH - DYE_LOW), 0.0, 1.0)


def fit_level(heights: np.ndarray, wetness: np.ndarray, quality: np.ndarray, floor_mm: float,
              rim_top_mm: float) -> LevelFit:
    """Best water level: predicted wet = ground below L, scored against observed wetness.

    Returns the plateau of levels whose score is within ``RANGE_MARGIN`` of the best.
    """
    candidates = np.arange(floor_mm, rim_top_mm + 1e-9, LEVEL_STEP_MM, dtype=np.float32)
    h = heights.astype(np.float32)[:, None]
    near = 1.0 + NEAR_BETA * np.exp(-np.abs(h - candidates[None, :]) / NEAR_SIGMA_MM)
    weight = quality.astype(np.float32)[:, None] * near
    w = wetness.astype(np.float32)[:, None]
    agree = np.where(h < candidates[None, :], w, 1.0 - w)
    score = (weight * agree).sum(axis=0) / weight.sum(axis=0)
    best = int(np.argmax(score))
    floor_score = score[best] - RANGE_MARGIN
    lo = hi = best
    while lo > 0 and score[lo - 1] >= floor_score:
        lo -= 1
    while hi < len(score) - 1 and score[hi + 1] >= floor_score:
        hi += 1
    return LevelFit(float(candidates[lo]), float(candidates[hi]), float(score[best]),
                    float(score[best] - score.min()))
