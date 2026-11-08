"""Water level reader: frame in, flood level (ft, range, confidence) and its meaning out."""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from dataclasses import asdict, dataclass, replace
from typing import Any

import cv2
import numpy as np

from .camera import Intrinsics, Pose, project, tello_default
from .fit import (CellGrid, build_cell_grid, dye_direction, fit_level, project_cells, sample_lab, to_lab,
                  visible_mask, wetness_from_baseline, wetness_from_dye)
from .model import TrayModel
from .pose import MIN_TAGS, PoseFix, detect_tags, estimate_focal, solve_pose
from .rim import RimFit, rim_alignment, rim_problem, solve_rim_pose

logger = logging.getLogger(__name__)

SMOOTH_WINDOW = 8
MIN_VISIBLE_CELLS = 1500
MIN_CONTRAST = 0.04
BASELINE_CAP, DYE_ONLY_CAP = 0.95, 0.6
AGREEMENT_FLOOR, AGREEMENT_SPAN = 0.7, 0.25
WIDTH_OK_MM, WIDTH_SPAN_MM = 2.5, 4.0
CELLS_FOR_FULL_CONFIDENCE = 2000
THREE_TAG_FACTOR = 0.85
POSE_FACTORS = {"corners": 0.95, "rim": 0.85}  # confidence factor by pose source (tags: 1.0 / 0.85)
SIGNATURE_SIZE = (80, 60)  # background thumbnail used to notice the camera moving
CAMERA_STILL_GRAY = 10.0  # mean grey change outside the tray (0-255) above this = camera moved
RESOLVE_MIN_SECONDS = 1.0  # don't retry a failed tag-free solve more often than this
TRAY_MASK_DILATE_PX = 3
MOVED_RIM_EXTRA_PX = 2.0  # dry-edge misalignment above the locked value by this = camera moved
EDGE_LABEL_INSET_MM = 4.0  # edge labels sit on the rim, this far in from the outer edge
REPROJ_OK_PX, REPROJ_SPAN_PX = 1.5, 3.0
BASELINE_MOVE_MM, BASELINE_MOVE_DEG = 25.0, 8.0
BASELINE_LEAVE_FRACTION = 0.7
INVALID_STREAK_TO_CLEAR = 3
INTRINSICS_SCALE_TOLERANCE = 0.02
OVERLAY_TEXT_PAD_PX = 2
WET_THRESHOLD = 0.5
BASELINE_WET_FRACTION = 0.03  # a 'dry' baseline with more of the visible tray looking dyed than this is refused
MIN_VIEW_DEG = 16.0  # shallower views hide the terraces and read a step off: withhold, ask to raise it
MIN_REPORT_FRACTION = 0.5  # withhold a reading below this share of its mode's top confidence
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
OVERLAY_DEEP_BGR = (120, 30, 0)  # deepest water is drawn darker blue
OVERLAY_DEEP_FT = 4.0  # depth at which the shading reaches OVERLAY_DEEP_BGR


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
    pose_source: str | None = None  # "tags", "corners" (clicked) or "rim" (auto outline)
    # Per place: CAD ground height vs the measured water surface. See location_depths().
    depths: tuple[dict[str, Any], ...] = ()

    @property
    def valid(self) -> bool:
        return self.level_mm is not None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("level_mm_range", "ft_range"):
            if data[key] is not None:
                data[key] = list(data[key])
        return {key: _finite_or_none(value) for key, value in data.items()}


def _finite_or_none(value: Any) -> Any:
    """NaN and infinity become None (JSON has no representation for them)."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (list, tuple)):
        return [_finite_or_none(v) for v in value]
    if isinstance(value, dict):
        return {k: _finite_or_none(v) for k, v in value.items()}
    return value


def _locations(model: TrayModel) -> list[tuple[str, str, float]]:
    """(id, label, CAD ground height mm) for the places the console reports depth at."""
    river = model.height_mm[model.river] if model.river.any() else model.height_mm
    places = [("river", "River channel", float(np.median(river))),
              ("crossing", "Low-water crossing", float(model.road.deck_mm)),
              ("car", "Stranded car", float(model.car.road_mm))]
    places += [(f"house_{i + 1}", f"House {i + 1}", float(h.ground_mm)) for i, h in enumerate(model.houses)]
    return places


def location_depths(model: TrayModel, level_mm: float, level_range_mm: tuple[float, float]) -> tuple[dict[str, Any], ...]:
    """The same logic as the real system: the CAD (like a terrain model) gives each place's ground height;
    vision gives the water surface. Depth = surface - ground (0 when dry); before = at normal pool.
    Feet use the tray scale (one terrace step = 1 ft)."""
    def feet(surface: float, ground: float) -> float:
        return round(max(0.0, surface - ground) / model.step_mm, 2)

    out = []
    for place, label, ground in _locations(model):
        before = feet(model.pool_mm, ground)
        now = feet(level_mm, ground)
        out.append({"id": place, "label": label, "ground_mm": round(ground, 2), "before_ft": before,
                    "now_ft": now, "now_ft_range": [feet(level_range_mm[0], ground), feet(level_range_mm[1], ground)],
                    "change_ft": round(now - before, 2), "flooded": level_mm > ground})
    return tuple(out)


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
    last_step = max(0, int(np.ceil((model.rim_top_mm - model.pool_mm) / model.step_mm - 1e-9)) - 1)
    k = min(k, last_step)
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


@dataclass(frozen=True, eq=False)
class _Analysis:
    """Tag detection and visibility for one frame object (kept alive so ``frame is`` identifies it)."""
    frame: np.ndarray
    shape: tuple[int, ...]
    seen: dict[int, np.ndarray]
    tags: int
    view: _View | None
    source: str | None = None
    problem: str | None = None


@dataclass(frozen=True, eq=False)
class _RimLock:
    """A tag-free pose held while the camera stays put (stand mode); re-solved when it moves."""
    fit: RimFit
    view: _View
    signature: np.ndarray  # background thumbnail (grey)
    background: np.ndarray  # True where the thumbnail is outside the tray
    rim_px: float  # dry-edge alignment when locked


class GaugeReader:
    """Reads the flood level from tray frames. Not thread-safe: use one reader per thread."""

    def __init__(self, model: TrayModel, cam: Intrinsics | None = None, dye: str = "blue",
                 facing: str | None = None) -> None:
        """facing="flood_watch": the tray is always placed with its FLOOD WATCH edge towards the camera,
        so the automatic outline needs no corner clicks."""
        self.model = model
        self._facing = facing
        self._cam_guess = cam
        self._direction = dye_direction(dye)
        self._grid: CellGrid = build_cell_grid(model)
        self._baseline: _Baseline | None = None
        self._focal_samples: list[float] = []
        self._refined_cam: Intrinsics | None = None
        self._buffer: deque[WaterEstimate] = deque(maxlen=SMOOTH_WINDOW)
        self._car_idx: int | None = None
        self._drops = 0
        self._invalid_streak = 0
        self._moved = False
        self._analysis: _Analysis | None = None
        self._rescale_logged: set[tuple[int, int]] = set()
        self._corners_px: np.ndarray | None = None
        self._rim_lock: _RimLock | None = None
        self._rim_problem: str | None = None
        self._last_rim_attempt = 0.0

    # ---------------------------------------------------------------- geometry
    def _guess_for(self, shape: tuple[int, int]) -> Intrinsics:
        """Intrinsics for a frame of this (h, w); a guess made for another size is rescaled to fit."""
        cam = self._cam_guess
        if cam is None:
            return tello_default(shape[1], shape[0])
        height, width = shape
        sx, sy = width / (2.0 * cam.cx), height / (2.0 * cam.cy)
        if abs(sx - 1.0) <= INTRINSICS_SCALE_TOLERANCE and abs(sy - 1.0) <= INTRINSICS_SCALE_TOLERANCE:
            return cam
        if (width, height) not in self._rescale_logged:
            self._rescale_logged.add((width, height))
            logger.info("frame %dx%d differs from the camera's implied %dx%d: rescaling intrinsics",
                        width, height, round(2 * cam.cx), round(2 * cam.cy))
        return replace(cam, fx=cam.fx * sx, fy=cam.fy * sy, cx=cam.cx * sx, cy=cam.cy * sy)

    def _analyse(self, frame: np.ndarray) -> _Analysis:
        """Detect tags and compute the view once per frame object; update() and overlay() share it."""
        cached = self._analysis
        if cached is not None and cached.frame is frame and cached.shape == frame.shape:
            return cached
        seen = self._detect(frame)
        tags = len([i for i in seen if i in self.model.tag_corners_mm])
        if tags >= MIN_TAGS:
            view = self._view(frame, seen)
            problem = None if view else "pose rejected: tags inconsistent or reprojection error too high"
            source = "tags" if view else None
        else:
            view, problem = self._rim_view(frame)
            source = self._rim_lock.fit.source if view is not None and self._rim_lock is not None else None
        self._analysis = _Analysis(frame, frame.shape, seen, tags, view, source, problem)
        return self._analysis

    # ---------------------------------------------------------------- tag-free pose
    def set_corners(self, points_px: Any) -> tuple[bool, str]:
        """Use 4 clicked rim corners (image px) for the pose: start at the left end of the FLOOD WATCH
        edge, then go around. Kept until cleared; the pose is re-solved from them if the camera moves."""
        try:
            pts = np.asarray(points_px, dtype=np.float64).reshape(4, 2)
        except (TypeError, ValueError):
            return False, "need exactly 4 corner points [[x, y], ...]"
        if not np.isfinite(pts).all() or len({tuple(np.round(p)) for p in pts}) < 4:
            return False, "corner points must be 4 distinct finite pixels"
        self._corners_px = pts
        self._forget_rim()
        return True, "ok"

    def clear_corners(self) -> None:
        self._corners_px = None
        self._forget_rim()

    @property
    def corners_px(self) -> list[list[float]] | None:
        return None if self._corners_px is None else self._corners_px.tolist()

    def _forget_rim(self) -> None:
        self._rim_lock, self._rim_problem, self._last_rim_attempt, self._analysis = None, None, 0.0, None

    def _rim_view(self, frame: np.ndarray) -> tuple[_View | None, str | None]:
        """Tag-free view: reuse the locked pose while the camera is still, else re-solve (rate-limited)."""
        lock = self._rim_lock
        if lock is not None and self._camera_still(frame, lock):
            return lock.view, None
        now = time.time()
        if self._rim_problem is not None and now - self._last_rim_attempt < RESOLVE_MIN_SECONDS:
            return None, self._rim_problem
        self._last_rim_attempt = now
        fit = solve_rim_pose(frame, self.model, self._guess_for(frame.shape[:2]), corners_px=self._corners_px,
                             facing=self._facing)
        problem = rim_problem(fit)
        if problem is not None or fit is None:
            self._rim_lock, self._rim_problem = None, problem
            return None, problem
        view = self._view_from(frame, fit.fix, fit.cam)
        signature, background = self._signature(frame, fit)
        rim_px = rim_alignment(frame, self.model, fit.cam, fit.fix.pose)
        self._rim_lock, self._rim_problem = _RimLock(fit, view, signature, background, rim_px), None
        return view, None

    def _tray_outline_px(self, fix: PoseFix, cam: Intrinsics) -> np.ndarray:
        w, d = self.model.size_mm[0], self.model.size_mm[1]
        corners = np.array([[x, y, z] for z in (0.0, self.model.rim_top_mm)
                            for x, y in ((0, 0), (w, 0), (w, d), (0, d))], dtype=np.float64)
        return project(corners, cam, fix.pose)[0]

    def _signature(self, frame: np.ndarray, fit: RimFit) -> tuple[np.ndarray, np.ndarray]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, SIGNATURE_SIZE, interpolation=cv2.INTER_AREA).astype(np.float32)
        scale = np.array([SIGNATURE_SIZE[0] / frame.shape[1], SIGNATURE_SIZE[1] / frame.shape[0]])
        hull = cv2.convexHull((self._tray_outline_px(fit.fix, fit.cam) * scale).astype(np.int32))
        tray = np.zeros((SIGNATURE_SIZE[1], SIGNATURE_SIZE[0]), np.uint8)
        cv2.fillConvexPoly(tray, hull, 1)
        tray = cv2.dilate(tray, np.ones((TRAY_MASK_DILATE_PX, TRAY_MASK_DILATE_PX), np.uint8))
        return small, tray == 0

    def _camera_still(self, frame: np.ndarray, lock: _RimLock) -> bool:
        """Still when the background looks the same AND the always-dry rim edges still line up.

        Water and hands change the inside of the tray, so neither check looks there."""
        if not lock.background.any():
            return False
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, SIGNATURE_SIZE, interpolation=cv2.INTER_AREA).astype(np.float32)
        if float(np.abs(small - lock.signature)[lock.background].mean()) >= CAMERA_STILL_GRAY:
            return False
        return rim_alignment(frame, self.model, lock.fit.cam, lock.fit.fix.pose) < lock.rim_px + MOVED_RIM_EXTRA_PX

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
        return self._view_from(frame, *solved)

    def _view_from(self, frame: np.ndarray, fix: PoseFix, cam: Intrinsics) -> _View:
        px, inside = project_cells(self._grid, cam, fix.pose, frame.shape[:2])
        idx = np.flatnonzero(inside)
        sub = CellGrid(self._grid.points_mm[idx], self._grid.height_mm[idx], self._grid.quality[idx])
        vis = visible_mask(sub, self.model, fix.camera_mm)
        return _View(fix, cam, px[idx[vis]], idx[vis])

    # ---------------------------------------------------------------- baseline
    def set_baseline(self, frame: np.ndarray) -> tuple[bool, str]:
        """Capture the dry drape. Returns (ok, reason)."""
        view = self._analyse(frame).view
        if view is None:
            return False, self._analyse(frame).problem or "can't find the tray"
        if len(view.cell_idx) < MIN_VISIBLE_CELLS:
            return False, f"only {len(view.cell_idx)} tray cells visible"
        lab_obs = sample_lab(to_lab(frame), view.px)
        if self._shows_water(lab_obs, view):
            return False, "tray already has water; capture the baseline dry"
        lab = np.full((len(self._grid.height_mm), 3), np.nan, dtype=np.float32)
        lab[view.cell_idx] = lab_obs
        self._baseline = _Baseline(view.fix.pose, view.fix.camera_mm, lab)
        self.reset()
        self._moved = False
        return True, "ok"

    def _shows_water(self, lab_obs: np.ndarray, view: _View) -> bool:
        """True when enough of the tray looks dyed AND that wetness forms a waterline above the floor.

        Requiring actual dyed cells matters: on a dry tray the level fit still "agrees" with an all-dry
        picture at the lowest plateau, which would otherwise read as water just above the floor."""
        wet = wetness_from_dye(lab_obs, self._direction)
        if float((wet > WET_THRESHOLD).mean()) < BASELINE_WET_FRACTION:
            return False
        fit = fit_level(self._grid.height_mm[view.cell_idx], wet, self._grid.quality[view.cell_idx],
                        self.model.floor_mm, self.model.rim_top_mm)
        return fit.contrast >= MIN_CONTRAST and fit.level_hi_mm > self.model.floor_mm + 0.5

    def clear_baseline(self) -> None:
        self._baseline = None
        self._moved = False

    def _baseline_shift(self, fix: PoseFix) -> tuple[float, float]:
        base = self._baseline
        assert base is not None
        move = float(np.linalg.norm(fix.camera_mm - base.camera_mm))
        axis_a, axis_b = base.pose.rotation[2], fix.pose.rotation[2]
        angle = float(np.degrees(np.arccos(np.clip(axis_a @ axis_b, -1.0, 1.0))))
        return move, angle

    def _update_moved(self, dist: float, angle: float) -> bool:
        """Moved-state with hysteresis: enter above the threshold, leave only below 70% of it."""
        if dist > BASELINE_MOVE_MM or angle > BASELINE_MOVE_DEG:
            self._moved = True
        elif dist < BASELINE_LEAVE_FRACTION * BASELINE_MOVE_MM and angle < BASELINE_LEAVE_FRACTION * BASELINE_MOVE_DEG:
            self._moved = False
        return self._moved

    # ---------------------------------------------------------------- reading
    def _none(self, reason: str, **kw: Any) -> WaterEstimate:
        return WaterEstimate(reason=reason, houses_total=len(self.model.houses), ts=time.time(), **kw)

    def _confidence(self, fit_agreement: float, width: float, visible: int, source_factor: float, err: float,
                    cap: float) -> float:
        quality = float(np.clip((fit_agreement - AGREEMENT_FLOOR) / AGREEMENT_SPAN, 0.0, 1.0))
        narrow = float(np.clip(1.0 - (width - WIDTH_OK_MM) / WIDTH_SPAN_MM, 0.0, 1.0))
        cells = min(1.0, visible / CELLS_FOR_FULL_CONFIDENCE)
        pose_factor = 1.0 - 0.5 * float(np.clip((err - REPROJ_OK_PX) / REPROJ_SPAN_PX, 0.0, 1.0))
        return float(np.clip(cap * quality * narrow * cells * source_factor * pose_factor, 0.0, 1.0))

    def _view_angle_deg(self, view: _View) -> float:
        """How far below horizontal the camera looks at the tray centre."""
        w, d = self.model.size_mm[0], self.model.size_mm[1]
        offset = np.asarray(view.fix.camera_mm, float) - np.array([w / 2, d / 2, self.model.rim_top_mm])
        return float(np.degrees(np.arctan2(offset[2], np.hypot(offset[0], offset[1]))))

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
        analysis = self._analyse(frame)
        if analysis.view is None:
            return self._none(analysis.problem or "can't find the tray", tags_seen=analysis.tags)
        return self._estimate(frame, analysis.view, analysis.tags, analysis.source or "tags")

    def _estimate(self, frame: np.ndarray, view: _View, tags: int, source: str) -> WaterEstimate:
        base_kw = dict(tags_seen=tags, reproj_err_px=view.fix.reproj_err_px, focal_px=view.cam.fx,
                       visible_cells=len(view.cell_idx), pose_source=source)
        if len(view.cell_idx) < MIN_VISIBLE_CELLS:
            return self._none("too few tray cells visible", **base_kw)
        view_deg = self._view_angle_deg(view)
        if view_deg < MIN_VIEW_DEG:
            return self._none(f"view too shallow ({view_deg:.0f} deg down, need {MIN_VIEW_DEG:.0f}+): raise the drone "
                              "or move it closer so it looks down on the tray more", **base_kw)
        moved, note = False, None
        if self._baseline is None:
            self._moved = False
        else:
            dist, angle = self._baseline_shift(view.fix)
            moved = self._update_moved(dist, angle)
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
        pose_factor = (1.0 if tags >= 4 else THREE_TAG_FACTOR) if source == "tags" else POSE_FACTORS[source]
        confidence = self._confidence(fit.agreement, fit.level_hi_mm - fit.level_lo_mm, int(valid.sum()),
                                      pose_factor, 0.0 if source != "tags" else view.fix.reproj_err_px,
                                      BASELINE_CAP if used_base else DYE_ONLY_CAP)
        if confidence < MIN_REPORT_FRACTION * (BASELINE_CAP if used_base else DYE_ONLY_CAP):
            return self._none(f"low confidence ({confidence:.2f}): too much of the tray is hidden at this angle. "
                              "Raise the drone or view the tray from another side.", **common)
        return self._meaning(WaterEstimate(level_mm=level, level_mm_range=level_range, ft=ft, ft_range=ft_range,
                                           confidence=confidence, reason=note, ts=time.time(),
                                           houses_total=len(self.model.houses), **common), self._car_idx)

    def _meaning(self, est: WaterEstimate, previous_car: int | None) -> WaterEstimate:
        assert est.level_mm is not None
        est = replace(est, depths=location_depths(self.model, est.level_mm, est.level_mm_range or (est.level_mm,) * 2))
        crossing, _, houses = describe_level(self.model, est.level_mm)
        car = CAR_LEVELS[_apply_car_hysteresis(self.model, est.level_mm, previous_car)]
        return replace(est, crossing_flooded=crossing, car_level=car, houses_flooded=houses)

    # ---------------------------------------------------------------- smoothing
    def reset(self) -> None:
        """Forget the smoothing history (the dry baseline is kept; see ``clear_baseline``)."""
        self._buffer.clear()
        self._car_idx = None
        self._drops = 0
        self._invalid_streak = 0

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
                       houses_flooded=houses, reason=note or latest.reason,
                       depths=location_depths(model, level, (lo, hi)))

    def update(self, frame: np.ndarray) -> WaterEstimate:
        """Smoothed estimate: median of the last valid frames; occluded or implausible frames are dropped."""
        est = self.read(frame)
        if not est.valid:
            if est.pose_source is None and est.tags_seen < MIN_TAGS:  # no pose at all (occluded): hold the last reading
                return self._smoothed(est, est.reason) if self._buffer else est
            self._drops = 0
            self._invalid_streak += 1
            if self._invalid_streak >= INVALID_STREAK_TO_CLEAR:
                self._buffer.clear()
                self._car_idx = None
            return est
        self._invalid_streak = 0
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
        analysis = self._analyse(frame)
        for corners in analysis.seen.values():
            cv2.polylines(out, [corners.astype(np.int32).reshape(-1, 1, 2)], True, (0, 255, 0), 2)
        view = analysis.view
        if view is not None and analysis.source in ("rim", "corners"):
            rim = self._tray_outline_px(view.fix, view.cam)[4:]
            cv2.polylines(out, [np.rint(rim).astype(np.int32).reshape(-1, 1, 2)], True, (0, 255, 0), 2)
            self._label_edges(out, view)
        if view is not None and estimate.level_mm is not None:
            depth_ft = (estimate.level_mm - self._grid.height_mm[view.cell_idx]) / self.model.step_mm
            wet = depth_ft > 0
            shade = np.zeros(frame.shape[:2], dtype=np.float32)  # 0 = dry, 1..2 = shallow..deep
            pts = np.rint(view.px[wet]).astype(int)
            shade[pts[:, 1], pts[:, 0]] = 1.0 + np.clip(depth_ft[wet] / OVERLAY_DEEP_FT, 0.0, 1.0)
            shade = cv2.dilate(shade, np.ones((3, 3), np.uint8))
            mask = shade > 0
            t = (shade[mask] - 1.0)[:, None]
            tint = (1 - t) * np.array(OVERLAY_TINT_BGR, np.float32) + t * np.array(OVERLAY_DEEP_BGR, np.float32)
            out[mask] = (out[mask] * (1 - OVERLAY_ALPHA) + tint * OVERLAY_ALPHA).astype(np.uint8)
        for row, text in enumerate(self._overlay_lines(estimate)):
            _draw_label(out, text, (10, 24 + 24 * row))
        return out

    def _label_edges(self, out: np.ndarray, view: _View) -> None:
        """Name two rim edges so a wrongly ordered click is obvious: the labels should sit on the
        tray's FLOOD WATCH and GUADALUPE RIVER edges. If they don't, click the corners again."""
        w, d, z = self.model.size_mm[0], self.model.size_mm[1], self.model.rim_top_mm
        spots = np.array([[w / 2, EDGE_LABEL_INSET_MM, z], [w / 2, d - EDGE_LABEL_INSET_MM, z]])
        px = project(spots, view.cam, view.fix.pose)[0]
        for text, (x, y) in zip(("FLOOD WATCH edge", "RIVER edge"), px):
            if np.isfinite(x) and np.isfinite(y):
                _draw_label(out, text, (int(x) - 60, int(y)))

    @staticmethod
    def _overlay_lines(est: WaterEstimate) -> list[str]:
        tag = " [SIMULATED]" if est.simulated else ""
        if est.ft is None or est.ft_range is None:
            return [f"Flood level: unknown ({est.reason}){tag}"]
        return [f"Flood level: {est.ft:.1f} ft (range {est.ft_range[0]:.0f}-{est.ft_range[1]:.0f}){tag}",
                f"confidence {est.confidence:.2f}  pose {est.pose_source}  baseline {est.has_baseline}",
                f"crossing {'FLOODED' if est.crossing_flooded else 'clear'}  car {est.car_level}  "
                f"houses {est.houses_flooded}/{est.houses_total}"]



def _draw_label(img: np.ndarray, text: str, origin: tuple[int, int]) -> None:
    """White text on a dark box, laid out once so the backing and glyphs always align."""
    font, scale, thickness = cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1
    (width, height), baseline = cv2.getTextSize(text, font, scale, thickness)
    x, y = origin
    pad = OVERLAY_TEXT_PAD_PX
    cv2.rectangle(img, (x - pad, y - height - pad), (x + width + pad, y + baseline + pad), (0, 0, 0), cv2.FILLED)
    cv2.putText(img, text, origin, font, scale, (255, 255, 255), thickness, cv2.LINE_AA)
