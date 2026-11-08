"""Water level reader: frame in, flood level (ft, range, confidence) and its meaning out."""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import asdict, dataclass, replace
from typing import Any

import cv2
import numpy as np

from .camera import Intrinsics, Pose, tello_default
from .fit import (CellGrid, build_cell_grid, dye_direction, fit_level, project_cells, sample_lab, to_lab,
                  visible_mask, wetness_from_baseline, wetness_from_dye)
from .model import TrayModel
from .pose import MIN_TAGS, PoseFix, detect_tags, estimate_focal, solve_pose

logger = logging.getLogger(__name__)

SMOOTH_WINDOW = 8
MIN_VISIBLE_CELLS = 1500
MIN_CONTRAST = 0.04
BASELINE_CAP, DYE_ONLY_CAP = 0.95, 0.6
AGREEMENT_FLOOR, AGREEMENT_SPAN = 0.7, 0.25
WIDTH_OK_MM, WIDTH_SPAN_MM = 2.5, 4.0
CELLS_FOR_FULL_CONFIDENCE = 2000
THREE_TAG_FACTOR = 0.85
REPROJ_OK_PX, REPROJ_SPAN_PX = 1.5, 3.0
BASELINE_MOVE_MM, BASELINE_MOVE_DEG = 12.0, 4.0
WET_THRESHOLD = 0.5
FOCAL_SAMPLES = 15
FOCAL_MIN_RATIO, FOCAL_MAX_RATIO = 0.5, 2.0
CAR_HYSTERESIS_MM = 0.3
WET_JUMP_LIMIT = 0.25
MAX_CONSECUTIVE_DROPS = 4
MIN_HISTORY_FOR_JUMP_CHECK = 3
CAR_LEVELS = ("none", "wheels", "doors", "windows", "roof")
WHEEL_HEIGHT_MM = 1.0
OVERLAY_TINT_BGR = (255, 120, 0)
OVERLAY_ALPHA = 0.4


@dataclass(frozen=True)
class WaterEstimate:
    level_mm: float | None = None
    level_mm_range: tuple[float, float] | None = None
    ft: float | None = None
    ft_range: tuple[float, float] | None = None
    confidence: float = 0.0
    crossing_flooded: bool | None = None
    car_level: str | None = None
    houses_flooded: int | None = None
    houses_total: int = 0
    visible_cells: int = 0
    wet_cells: int = 0
    tags_seen: int = 0
    reproj_err_px: float | None = None
    has_baseline: bool = False
    simulated: bool = False
    reason: str | None = None
    ts: float = 0.0
    baseline_moved: bool = False
    wet_fraction: float = 0.0
    focal_px: float | None = None

    @property
    def valid(self) -> bool:
        return self.level_mm is not None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("level_mm_range", "ft_range"):
            if data[key] is not None:
                data[key] = list(data[key])
        return data


def car_level_index(model: TrayModel, level: float) -> int:
    bounds = (model.car.road_mm, model.car.road_mm + WHEEL_HEIGHT_MM, model.car.body_top_mm, model.car.roof_mm)
    return int(sum(level >= b for b in bounds))


def describe_level(model: TrayModel, level: float) -> tuple[bool, str, int]:
    """Meaning of a water level: (crossing flooded, car level, houses flooded)."""
    houses = sum(1 for h in model.houses if h.ground_mm < level)
    return level > model.road.deck_mm, CAR_LEVELS[car_level_index(model, level)], houses


def _apply_car_hysteresis(model: TrayModel, level: float, previous: int | None) -> int:
    target = car_level_index(model, level)
    if previous is None:
        return target
    bounds = (model.car.road_mm, model.car.road_mm + WHEEL_HEIGHT_MM, model.car.body_top_mm, model.car.roof_mm)
    idx = previous
    while idx < target and level >= bounds[idx] + CAR_HYSTERESIS_MM:
        idx += 1
    while idx > target and level < bounds[idx - 1] - CAR_HYSTERESIS_MM:
        idx -= 1
    return idx


def _step_interval(model: TrayModel, lo: float, hi: float) -> tuple[float, tuple[float, float], float, tuple[float, float]]:
    """Snap an equivalent-level plateau to the 1 ft step it lies in: (level, range, ft, ft_range)."""
    k = int(np.floor(((lo + hi) / 2.0 - model.pool_mm) / model.step_mm + 1e-9))
    if k < 0:
        return model.pool_mm, (max(model.floor_mm, model.pool_mm + k * model.step_mm), model.pool_mm), 0.0, (0.0, 0.0)
    low = model.pool_mm + k * model.step_mm
    high = min(low + model.step_mm, model.rim_top_mm)
    return (low + high) / 2.0, (low, high), k + 0.5, (float(k), float(k + 1))


@dataclass(frozen=True, eq=False)
class _Baseline:
    pose: Pose
    camera_mm: np.ndarray
    lab: np.ndarray  # (N, 3) per grid cell, NaN where unseen


@dataclass(frozen=True, eq=False)
class _View:
    fix: PoseFix
    cam: Intrinsics
    px: np.ndarray        # (M, 2) of the in-frame cells
    cell_idx: np.ndarray  # indices into the grid of the visible, in-frame cells


class GaugeReader:
    """Reads the flood level from tray frames. Not thread-safe: use one reader per thread."""

    def __init__(self, model: TrayModel, cam: Intrinsics | None = None, dye: str = "blue") -> None:
        self.model = model
        self._cam_guess = cam
        self._direction = dye_direction(dye)
        self._grid: CellGrid = build_cell_grid(model)
        self._baseline: _Baseline | None = None
        self._focal_samples: list[float] = []
        self._refined_cam: Intrinsics | None = None
        self._buffer: deque[WaterEstimate] = deque(maxlen=SMOOTH_WINDOW)
        self._car_idx: int | None = None
        self._drops = 0

    # ---------------------------------------------------------------- geometry
    def _guess_for(self, shape: tuple[int, int]) -> Intrinsics:
        return self._cam_guess if self._cam_guess is not None else tello_default(shape[1], shape[0])

    def _solve(self, seen: dict[int, np.ndarray], shape: tuple[int, int]) -> tuple[PoseFix, Intrinsics] | None:
        """Pose with the given intrinsics and with a tag-derived focal; keep the better fit."""
        guess = self._guess_for(shape)
        focal = estimate_focal(seen, self.model, shape[1], shape[0])
        if focal is not None and FOCAL_MIN_RATIO * guess.fx <= focal <= FOCAL_MAX_RATIO * guess.fx:
            self._focal_samples = (self._focal_samples + [focal])[-FOCAL_SAMPLES:]
            median = float(np.median(self._focal_samples))
            self._refined_cam = replace(guess, fx=median, fy=median)
        options = [guess] + ([self._refined_cam] if self._refined_cam is not None else [])
        fixes = [(solve_pose(seen, self.model, c), c) for c in options]
        fixes = [(f, c) for f, c in fixes if f is not None]
        if not fixes:
            return None
        return min(fixes, key=lambda fc: fc[0].reproj_err_px)

    def _detect(self, frame: np.ndarray) -> dict[int, np.ndarray]:
        return detect_tags(frame, self.model.tag_dictionary)

    def _view(self, frame: np.ndarray, seen: dict[int, np.ndarray]) -> _View | None:
        solved = self._solve(seen, frame.shape[:2])
        if solved is None:
            return None
        fix, cam = solved
        px, inside = project_cells(self._grid, cam, fix.pose, frame.shape[:2])
        idx = np.flatnonzero(inside)
        sub = CellGrid(self._grid.points_mm[idx], self._grid.height_mm[idx], self._grid.quality[idx])
        vis = visible_mask(sub, self.model, fix.camera_mm)
        return _View(fix, cam, px[idx[vis]], idx[vis])

    # ---------------------------------------------------------------- baseline
    def set_baseline(self, frame: np.ndarray) -> tuple[bool, str]:
        """Capture the dry drape. Returns (ok, reason)."""
        seen = self._detect(frame)
        if len(seen) < MIN_TAGS:
            return False, f"only {len(seen)} tags visible, need {MIN_TAGS}"
        view = self._view(frame, seen)
        if view is None:
            return False, "pose rejected (tags inconsistent or reprojection error too high)"
        if len(view.cell_idx) < MIN_VISIBLE_CELLS:
            return False, f"only {len(view.cell_idx)} tray cells visible"
        lab = np.full((len(self._grid.height_mm), 3), np.nan, dtype=np.float32)
        lab[view.cell_idx] = sample_lab(to_lab(frame), view.px)
        self._baseline = _Baseline(view.fix.pose, view.fix.camera_mm, lab)
        return True, "ok"

    def clear_baseline(self) -> None:
        self._baseline = None

    def _baseline_shift(self, fix: PoseFix) -> tuple[float, float]:
        base = self._baseline
        assert base is not None
        move = float(np.linalg.norm(fix.camera_mm - base.camera_mm))
        axis_a, axis_b = base.pose.rotation[2], fix.pose.rotation[2]
        angle = float(np.degrees(np.arccos(np.clip(axis_a @ axis_b, -1.0, 1.0))))
        return move, angle

    # ---------------------------------------------------------------- reading
    def _none(self, reason: str, **kw: Any) -> WaterEstimate:
        return WaterEstimate(reason=reason, houses_total=len(self.model.houses), ts=time.time(), **kw)

    def _confidence(self, fit_agreement: float, width: float, visible: int, tags: int, err: float,
                    cap: float) -> float:
        quality = float(np.clip((fit_agreement - AGREEMENT_FLOOR) / AGREEMENT_SPAN, 0.0, 1.0))
        narrow = float(np.clip(1.0 - (width - WIDTH_OK_MM) / WIDTH_SPAN_MM, 0.0, 1.0))
        cells = min(1.0, visible / CELLS_FOR_FULL_CONFIDENCE)
        tag_factor = 1.0 if tags >= 4 else THREE_TAG_FACTOR
        pose_factor = 1.0 - 0.5 * float(np.clip((err - REPROJ_OK_PX) / REPROJ_SPAN_PX, 0.0, 1.0))
        return float(np.clip(cap * quality * narrow * cells * tag_factor * pose_factor, 0.0, 1.0))

    def _wetness(self, lab_obs: np.ndarray, view: _View, moved: bool) -> tuple[np.ndarray, np.ndarray, bool]:
        """Wetness, validity mask and whether the baseline was used."""
        base = None if (self._baseline is None or moved) else self._baseline.lab[view.cell_idx]
        if base is None:
            return wetness_from_dye(lab_obs, self._direction), np.ones(len(lab_obs), dtype=bool), False
        ok = np.isfinite(base[:, 0])
        if ok.sum() < MIN_VISIBLE_CELLS:
            return wetness_from_dye(lab_obs, self._direction), np.ones(len(lab_obs), dtype=bool), False
        w = np.zeros(len(lab_obs))
        w[ok] = wetness_from_baseline(lab_obs[ok], base[ok], self._direction)
        return w, ok, True

    def read(self, frame: np.ndarray) -> WaterEstimate:
        """One-frame estimate (no smoothing)."""
        if frame is None or getattr(frame, "ndim", 0) != 3:
            return self._none("no frame")
        seen = self._detect(frame)
        tags = len([i for i in seen if i in self.model.tag_corners_mm])
        if tags < MIN_TAGS:
            return self._none(f"only {tags} of 4 tags visible", tags_seen=tags)
        view = self._view(frame, seen)
        if view is None:
            return self._none("pose rejected: tags inconsistent or reprojection error too high", tags_seen=tags)
        return self._estimate(frame, view, tags)

    def _estimate(self, frame: np.ndarray, view: _View, tags: int) -> WaterEstimate:
        base_kw = dict(tags_seen=tags, reproj_err_px=view.fix.reproj_err_px, focal_px=view.cam.fx,
                       visible_cells=len(view.cell_idx))
        if len(view.cell_idx) < MIN_VISIBLE_CELLS:
            return self._none("too few tray cells visible", **base_kw)
        moved, note = False, None
        if self._baseline is not None:
            dist, angle = self._baseline_shift(view.fix)
            moved = dist > BASELINE_MOVE_MM or angle > BASELINE_MOVE_DEG
            if moved:
                note = (f"baseline invalid: camera moved {dist:.0f} mm / {angle:.1f} deg since capture; "
                        "using dye colour only")
        lab_obs = sample_lab(to_lab(frame), view.px)
        wet, valid, used_base = self._wetness(lab_obs, view, moved)
        heights, quality = self._grid.height_mm[view.cell_idx][valid], self._grid.quality[view.cell_idx][valid]
        fit = fit_level(heights, wet[valid], quality, self.model.floor_mm, self.model.rim_top_mm)
        wet_cells = int((wet[valid] > WET_THRESHOLD).sum())
        common = dict(base_kw, has_baseline=used_base, baseline_moved=moved, wet_cells=wet_cells,
                      wet_fraction=wet_cells / max(1, int(valid.sum())))
        if fit.contrast < MIN_CONTRAST:
            return self._none("no clear waterline: score is flat", **common)
        if fit.level_hi_mm <= self.model.floor_mm + 0.5:
            return self._none("no water detected", **common)
        level, level_range, ft, ft_range = _step_interval(self.model, fit.level_lo_mm, fit.level_hi_mm)
        confidence = self._confidence(fit.agreement, fit.level_hi_mm - fit.level_lo_mm, int(valid.sum()), tags,
                                      view.fix.reproj_err_px, BASELINE_CAP if used_base else DYE_ONLY_CAP)
        return self._meaning(WaterEstimate(level_mm=level, level_mm_range=level_range, ft=ft, ft_range=ft_range,
                                           confidence=confidence, reason=note, ts=time.time(),
                                           houses_total=len(self.model.houses), **common), self._car_idx)

    def _meaning(self, est: WaterEstimate, previous_car: int | None) -> WaterEstimate:
        assert est.level_mm is not None
        crossing, _, houses = describe_level(self.model, est.level_mm)
        car = CAR_LEVELS[_apply_car_hysteresis(self.model, est.level_mm, previous_car)]
        return replace(est, crossing_flooded=crossing, car_level=car, houses_flooded=houses)

    # ---------------------------------------------------------------- smoothing
    def reset(self) -> None:
        """Forget the smoothing history (the dry baseline is kept; see ``clear_baseline``)."""
        self._buffer.clear()
        self._car_idx = None
        self._drops = 0

    def _implausible(self, est: WaterEstimate) -> bool:
        if len(self._buffer) < MIN_HISTORY_FOR_JUMP_CHECK:
            return False
        recent = float(np.median([e.wet_fraction for e in list(self._buffer)[-MIN_HISTORY_FOR_JUMP_CHECK:]]))
        return abs(est.wet_fraction - recent) > WET_JUMP_LIMIT

    def _smoothed(self, latest: WaterEstimate, note: str | None) -> WaterEstimate:
        items = list(self._buffer)
        levels = sorted(e.level_mm for e in items if e.level_mm is not None)
        level = levels[len(levels) // 2]
        lows = [e.level_mm_range[0] for e in items if e.level_mm_range]
        highs = [e.level_mm_range[1] for e in items if e.level_mm_range]
        lo = min(float(np.median(lows)), float(np.percentile(levels, 10)))
        hi = max(float(np.median(highs)), float(np.percentile(levels, 90)))
        model = self.model
        ft = max(0.0, (level - model.pool_mm) / model.step_mm)
        ft_range = (max(0.0, (lo - model.pool_mm) / model.step_mm), max(0.0, (hi - model.pool_mm) / model.step_mm))
        conf = float(np.median([e.confidence for e in items])) * min(1.0, len(items) / MIN_HISTORY_FOR_JUMP_CHECK)
        self._car_idx = _apply_car_hysteresis(model, level, self._car_idx)
        crossing, _, houses = describe_level(model, level)
        return replace(latest, level_mm=level, level_mm_range=(lo, hi), ft=ft, ft_range=ft_range,
                       confidence=conf, crossing_flooded=crossing, car_level=CAR_LEVELS[self._car_idx],
                       houses_flooded=houses, reason=note or latest.reason)

    def update(self, frame: np.ndarray) -> WaterEstimate:
        """Smoothed estimate: median of the last valid frames; occluded or implausible frames are dropped."""
        est = self.read(frame)
        if not est.valid:
            return self._smoothed(est, est.reason) if self._buffer and est.tags_seen < MIN_TAGS else est
        if self._implausible(est) and self._drops < MAX_CONSECUTIVE_DROPS:
            self._drops += 1
            return self._smoothed(est, "frame dropped: wet fraction jumped implausibly")
        if self._drops >= MAX_CONSECUTIVE_DROPS:
            self._buffer.clear()
        self._drops = 0
        self._buffer.append(est)
        return self._smoothed(est, None)

    # ---------------------------------------------------------------- overlay
    def overlay(self, frame: np.ndarray, estimate: WaterEstimate) -> np.ndarray:
        """Frame with tags outlined, cells predicted wet tinted and the reading as text."""
        out = frame.copy()
        seen = self._detect(frame)
        for corners in seen.values():
            cv2.polylines(out, [corners.astype(np.int32).reshape(-1, 1, 2)], True, (0, 255, 0), 2)
        view = self._view(frame, seen) if len(seen) >= MIN_TAGS else None
        if view is not None and estimate.level_mm is not None:
            wet = self._grid.height_mm[view.cell_idx] < estimate.level_mm
            mask = np.zeros(frame.shape[:2], dtype=np.uint8)
            pts = np.rint(view.px[wet]).astype(int)
            mask[pts[:, 1], pts[:, 0]] = 1
            mask = cv2.dilate(mask, np.ones((3, 3), np.uint8)).astype(bool)
            tint = np.array(OVERLAY_TINT_BGR, dtype=np.float32)
            out[mask] = (out[mask] * (1 - OVERLAY_ALPHA) + tint * OVERLAY_ALPHA).astype(np.uint8)
        for row, text in enumerate(self._overlay_lines(estimate)):
            cv2.putText(out, text, (10, 24 + 24 * row), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
            cv2.putText(out, text, (10, 24 + 24 * row), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        return out

    @staticmethod
    def _overlay_lines(est: WaterEstimate) -> list[str]:
        tag = " [SIMULATED]" if est.simulated else ""
        if est.ft is None or est.ft_range is None:
            return [f"Flood level: unknown ({est.reason}){tag}"]
        return [f"Flood level: {est.ft:.1f} ft (range {est.ft_range[0]:.0f}-{est.ft_range[1]:.0f}){tag}",
                f"confidence {est.confidence:.2f}  tags {est.tags_seen}  baseline {est.has_baseline}",
                f"crossing {'FLOODED' if est.crossing_flooded else 'clear'}  car {est.car_level}  "
                f"houses {est.houses_flooded}/{est.houses_total}"]

