"""Tag-free camera pose: find the tray from its own shape.

The tray is a 160 x 160 mm box with an 8 mm rim at a known height and a terrain whose every edge
(rim drop, terraces, river banks, houses) is in the CAD heightmap. So:

1. rough pose: the tray's outline in the image is close to a quadrilateral; PnP on its 4 corners
   (either the clicked corners or the detected outline) for every way the square could be turned,
2. snap: move the camera (and focal length) until the projected CAD edges land on image edges
   (truncated chamfer distance over a Canny distance transform),
3. orientation: the terrain is not symmetric, so only the true rotation lines up. If two rotations
   score about the same the answer is "unsure", not a guess.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from functools import lru_cache

import cv2
import numpy as np

from .camera import Intrinsics, Pose, camera_position_mm, project
from .model import TrayModel
from .pose import PoseFix

logger = logging.getLogger(__name__)

EDGE_STEP_MM = 0.8  # height change between neighbouring cells above this is a visible edge
EDGE_POINTS = 2400  # CAD edge points used for alignment (subsampled, fixed seed)
BOUNDARY_POINTS_PER_SIDE = 60
CHAMFER_CAP_PX = 12.0  # distances are truncated here so clutter can't dominate
CANNY_LO, CANNY_HI = 40, 120
MAX_MEAN_CHAMFER_PX = 7.0  # true poses score 2-5 px on a cluttered tray; far above means wrong
AMBIGUITY_RATIO = 0.75  # auto mode: best orientation must beat the runner-up by a third
CLICK_OVERRIDE_MARGIN = 1.15  # clicked order is trusted unless another rotation fits this much better
MIN_QUAD_AREA_FRAC, MAX_QUAD_AREA_FRAC = 0.01, 0.9
QUAD_EPS_FRACS = (0.01, 0.015, 0.02, 0.03, 0.04, 0.06, 0.08)
CLOSE_KERNEL_PX, CLOSE_ITERS = 7, 2
# Coordinate-descent step sizes: rotation (rad), translation (mm), focal (px), then a shrink schedule.
BASE_STEPS = np.array([0.02, 0.02, 0.02, 6.0, 6.0, 6.0, 30.0])
QUICK_SCHEDULE = (1.0, 0.5)
FULL_SCHEDULE = (1.0, 0.5, 0.25, 0.12, 0.06, 0.03)
TRACK_SCHEDULE = (0.12, 0.06, 0.03)
MAX_ROUNDS = 6
FOCAL_LIMITS = (0.7, 1.4)  # refined focal stays within this ratio of the starting guess
TOP_CANDIDATES = 3
FACING_TOLERANCE_DEG = 60.0  # 'FLOOD WATCH edge faces the drone' allows this much off-axis
FACINGS = ("flood_watch",)  # supported placement rules (None = any orientation, decided by the terrain)
DRY_EDGE_BELOW_RIM_MM = 0.5  # rim lip edges sit within this of the rim top


@dataclass(frozen=True, eq=False)
class RimFit:
    fix: PoseFix  # reproj_err_px holds the mean chamfer distance (px)
    cam: Intrinsics
    score_px: float
    margin: float  # runner-up orientation score / best score (> 1 = clear winner)
    source: str  # "rim" (detected outline) or "corners" (clicked)


@lru_cache(maxsize=4)
def _edge_points(model: TrayModel) -> np.ndarray:
    """CAD edge points (N, 3): every height step in the heightmap plus the tray's outer outline."""
    h, res = model.height_mm.astype(np.float64), model.res_mm
    pts = []
    for axis in (0, 1):
        step = np.abs(np.diff(h, axis=axis))
        iy, ix = np.nonzero(step > EDGE_STEP_MM)
        if axis == 1:
            x, y, lo, hi = (ix + 0.5) * res, iy * res, h[iy, ix], h[iy, ix + 1]
        else:
            x, y, lo, hi = ix * res, (iy + 0.5) * res, h[iy, ix], h[iy + 1, ix]
        # A step shows as two image edges: its top lip and its foot.
        pts.append(np.stack([x, y, np.maximum(lo, hi)], axis=1))
        pts.append(np.stack([x, y, np.minimum(lo, hi)], axis=1))
    edges = np.concatenate(pts)
    rng = np.random.default_rng(7)
    if len(edges) > EDGE_POINTS:
        edges = edges[rng.choice(len(edges), EDGE_POINTS, replace=False)]
    return np.concatenate([edges, _outline(model, model.rim_top_mm), _outline(model, 0.0)])


def _outline(model: TrayModel, z: float) -> np.ndarray:
    w, d = model.size_mm[0], model.size_mm[1]
    t = np.linspace(0.0, 1.0, BOUNDARY_POINTS_PER_SIDE, endpoint=False)
    sides = [np.stack([t * w, 0 * t, 0 * t + z], 1), np.stack([w + 0 * t, t * d, 0 * t + z], 1),
             np.stack([w - t * w, d + 0 * t, 0 * t + z], 1), np.stack([0 * t, d - t * d, 0 * t + z], 1)]
    return np.concatenate(sides)


def _corners(model: TrayModel, z_near: float, z_far: float, near: tuple[bool, ...]) -> np.ndarray:
    w, d = model.size_mm[0], model.size_mm[1]
    xy = [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]
    return np.array([[x, y, z_near if n else z_far] for (x, y), n in zip(xy, near)], dtype=np.float64)


@lru_cache(maxsize=4)
def _dry_points(model: TrayModel) -> np.ndarray:
    """Edges water can never reach: the rim lip, the corner pads and the tray's outline."""
    pts = _edge_points(model)
    return pts[(pts[:, 2] >= model.rim_top_mm - DRY_EDGE_BELOW_RIM_MM) | (pts[:, 2] <= 0.0)]


def rim_alignment(frame_bgr: np.ndarray, model: TrayModel, cam: Intrinsics, pose: Pose) -> float:
    """How well the always-dry edges line up with this pose (mean px). Rises when the camera moves."""
    return _score(edge_distance(frame_bgr), _dry_points(model), cam, pose)


def edge_distance(frame_bgr: np.ndarray) -> np.ndarray:
    """Distance (px) from every pixel to the nearest image edge, truncated at CHAMFER_CAP_PX."""
    gray = cv2.GaussianBlur(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    edges = cv2.Canny(gray, CANNY_LO, CANNY_HI)
    dt = cv2.distanceTransform(255 - edges, cv2.DIST_L2, 3)
    return np.minimum(dt, CHAMFER_CAP_PX).astype(np.float32)


def _score(dt: np.ndarray, pts: np.ndarray, cam: Intrinsics, pose: Pose) -> float:
    """Mean truncated distance from projected CAD edges to image edges; off-frame points cost the cap."""
    px, depth = project(pts, cam, pose)
    h, w = dt.shape
    ok = (depth > 0) & np.isfinite(px).all(axis=1)
    x, y = px[:, 0], px[:, 1]
    ok &= (x >= 0) & (y >= 0) & (x <= w - 1) & (y <= h - 1)
    cost = np.full(len(pts), CHAMFER_CAP_PX, dtype=np.float64)
    cost[ok] = dt[y[ok].astype(np.int64), x[ok].astype(np.int64)]
    return float(cost.mean())


def _unpack(x: np.ndarray, cam: Intrinsics) -> tuple[Pose, Intrinsics]:
    return Pose(x[:3].copy(), x[3:6].copy()), replace(cam, fx=float(x[6]), fy=float(x[6]))


def _descend(dt: np.ndarray, pts: np.ndarray, cam: Intrinsics, pose: Pose,
             schedule: tuple[float, ...]) -> tuple[Pose, Intrinsics, float]:
    """Coordinate descent over rotation, translation and focal length."""
    x = np.concatenate([np.asarray(pose.rvec, float).ravel(), np.asarray(pose.tvec, float).ravel(), [cam.fx]])
    f_lo, f_hi = FOCAL_LIMITS[0] * cam.fx, FOCAL_LIMITS[1] * cam.fx
    pose0, cam0 = _unpack(x, cam)
    best = _score(dt, pts, cam0, pose0)
    for scale in schedule:
        for _ in range(MAX_ROUNDS):
            improved = False
            for i in range(len(x)):
                for sign in (1.0, -1.0):
                    cand = x.copy()
                    cand[i] += sign * scale * BASE_STEPS[i]
                    if not f_lo <= cand[6] <= f_hi:
                        continue
                    pose_c, cam_c = _unpack(cand, cam)
                    s = _score(dt, pts, cam_c, pose_c)
                    if s < best:
                        x, best, improved = cand, s, True
            if not improved:
                break
    pose_out, cam_out = _unpack(x, cam)
    return pose_out, cam_out, best


def detect_tray_quads(frame_bgr: np.ndarray) -> list[np.ndarray]:
    """Candidate tray outlines (4x2 image points, clockwise), largest first."""
    h, w = frame_bgr.shape[:2]
    gray = cv2.GaussianBlur(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (CLOSE_KERNEL_PX, CLOSE_KERNEL_PX))
    quads = []
    for mask in _outline_masks(gray, kernel):
        quads += _quads_from(mask, h, w)
    return quads


def _outline_masks(gray: np.ndarray, kernel: np.ndarray) -> list[np.ndarray]:
    """Two independent ways to separate the tray from the table: closed edges, and brightness
    (Otsu threshold, both polarities, for a light tray on a dark table or the reverse)."""
    edges = cv2.morphologyEx(cv2.Canny(gray, CANNY_LO, CANNY_HI), cv2.MORPH_CLOSE, kernel, iterations=CLOSE_ITERS)
    _, bright = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    masks = [edges]
    for m in (bright, 255 - bright):
        masks.append(cv2.morphologyEx(cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel), cv2.MORPH_CLOSE, kernel,
                                      iterations=CLOSE_ITERS))
    return masks


def _quads_from(mask: np.ndarray, h: int, w: int) -> list[np.ndarray]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    quads = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:TOP_CANDIDATES]:
        hull = cv2.convexHull(contour)
        area = cv2.contourArea(hull) / float(h * w)
        if not MIN_QUAD_AREA_FRAC <= area <= MAX_QUAD_AREA_FRAC:
            continue
        perimeter = cv2.arcLength(hull, True)
        for eps in QUAD_EPS_FRACS:
            approx = cv2.approxPolyDP(hull, eps * perimeter, True)
            if len(approx) == 4:
                quads.append(_clockwise(approx.reshape(4, 2).astype(np.float64)))
                break
    return quads


def _clockwise(quad: np.ndarray) -> np.ndarray:
    centre = quad.mean(axis=0)
    angles = np.arctan2(quad[:, 1] - centre[1], quad[:, 0] - centre[0])
    return quad[np.argsort(angles)]


def _hypotheses(model: TrayModel, quad: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """(object corners, image corners) for each rotation and winding of the square.

    The two image corners lowest in the frame are usually the near side, where the outline is the
    tray's bottom edge (z = 0) rather than the rim top, so both height assignments are tried.
    """
    near = tuple(bool(v) for v in quad[:, 1] >= np.sort(quad[:, 1])[-2])
    out = []
    for winding in (quad, quad[::-1].copy()):
        near_w = near if winding is quad else near[::-1]
        for shift in range(4):
            img = np.roll(winding, shift, axis=0)
            flags = tuple(np.roll(np.array(near_w), shift))
            for z_near in (model.rim_top_mm, 0.0):
                out.append((_corners(model, z_near, model.rim_top_mm, flags), img))
    return out


DIFFERENT_ORIENTATION_DEG = 45.0  # rival hypotheses for a square tray differ by about 90 deg


def _differs(a: Pose, b: Pose) -> bool:
    """True when two poses put the tray at clearly different rotations."""
    cos = (np.trace(a.rotation.T @ b.rotation) - 1.0) / 2.0
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))) > DIFFERENT_ORIENTATION_DEG


def solve_clicked_pose(frame_bgr: np.ndarray, model: TrayModel, cam: Intrinsics,
                       corners_px: np.ndarray) -> RimFit | None:
    """Pose from 4 clicked rim-top corners in order: (0,0), (W,0), (W,D), (0,D) in tray mm.

    That is: start at the left end of the FLOOD WATCH edge, go along it, then around the tray.
    The clicked order is trusted; another rotation is used only if it fits clearly better.
    """
    dt = edge_distance(frame_bgr)
    pts = _edge_points(model)
    img = np.asarray(corners_px, np.float64).reshape(4, 2)
    obj = _corners(model, model.rim_top_mm, model.rim_top_mm, (False,) * 4)
    # "Go round" from the first click can mean clockwise or counter-clockwise depending on which side
    # the camera views from, so try both directions; the first click stays corner (0, 0) either way.
    forward, backward = img, np.roll(img[::-1], 1, axis=0)
    starts = []
    for direction in (forward, backward):
        for shift in range(4):
            ok, rvec, tvec = cv2.solvePnP(obj, np.roll(direction, -shift, axis=0), cam.matrix, cam.dist_array,
                                          flags=cv2.SOLVEPNP_IPPE)
            start = Pose(rvec.reshape(3), tvec.reshape(3))
            if ok and camera_position_mm(start)[2] > model.rim_top_mm:  # camera above the table
                starts.append((shift, start, _score(dt, pts, cam, start)))
    if not starts:
        return None
    # Pick the rotation on the raw corner fit: snapping first lets a wrong rotation half-fit the terrain.
    clicked = min((s for s in starts if s[0] == 0), key=lambda s: s[2], default=None)
    best = min(starts, key=lambda s: s[2])
    chosen = clicked if clicked is not None and clicked[2] <= best[2] * CLICK_OVERRIDE_MARGIN else best
    if chosen is not clicked:
        logger.info("clicked corners look rotated by %d; using the better-fitting rotation", chosen[0])
    pose, cam_out, score = _descend(dt, pts, cam, chosen[1], FULL_SCHEDULE)
    return RimFit(PoseFix(pose, score, (), camera_position_mm(pose)), cam_out, score, float("inf"), "corners")


def _faces(model: TrayModel, pose: Pose, facing: str | None) -> bool:
    """With facing="flood_watch" the camera must be in front of the FLOOD WATCH (y = 0) edge."""
    if facing is None:
        return True
    w, d = model.size_mm[0], model.size_mm[1]
    cam = camera_position_mm(pose)
    off_axis = np.degrees(np.arctan2(abs(cam[0] - w / 2), (d / 2) - cam[1]))
    return cam[1] < d / 2 and off_axis <= FACING_TOLERANCE_DEG


def _oriented_distances(gray: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Distance to edges parallel to each candidate projected rim direction."""
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
    normal = np.arctan2(gy, gx)
    bins = 12
    oriented = []
    for angle in np.arange(bins) * np.pi / bins:
        aligned = (edges > 0) & (np.abs(np.sin(normal - angle)) > np.cos(np.radians(20)))
        oriented.append(np.minimum(cv2.distanceTransform((~aligned).astype(np.uint8), cv2.DIST_L2, 3),
                                   CHAMFER_CAP_PX))
    return np.stack(oriented)


def _stand_fit(frame: np.ndarray, model: TrayModel, cam: Intrinsics) -> tuple[float, Pose]:
    """Fit the level stand setup, using all four sides of the elevated rim."""
    gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    edges = cv2.Canny(gray, 8, 24)
    dt = np.minimum(cv2.distanceTransform(255 - edges, cv2.DIST_L2, 3), CHAMFER_CAP_PX)
    oriented = _oriented_distances(gray, edges)
    bins = len(oriented)
    # Subsample the terrain during the search. The winning pose gets a full-resolution score.
    terrain = _edge_points(model)[::6]
    outline = _outline(model, model.rim_top_mm)
    centre = np.array([*np.divide(model.size_mm[:2], 2), model.rim_top_mm])

    def evaluate(params):
        angle, back, height, lateral = params
        a = np.radians(angle)
        forward = np.array([np.cos(a), np.sin(a), 0.])
        right = np.array([np.sin(a), -np.cos(a), 0.])
        rotation = np.stack((right, [0., 0., -1.], forward))
        position = centre - back * forward + np.array([0., 0., height]) + lateral * right
        pose = Pose(cv2.Rodrigues(rotation)[0].ravel(), -rotation @ position)
        px, _ = project(outline, cam, pose)
        xy = np.rint(px).astype(int)
        h, w = dt.shape
        visible = (xy[:, 0] >= 0) & (xy[:, 0] < w) & (xy[:, 1] >= 0) & (xy[:, 1] < h)
        cost = np.full(len(xy), CHAMFER_CAP_PX)
        corners = px[::BOUNDARY_POINTS_PER_SIDE]
        vectors = np.roll(corners, -1, axis=0) - corners
        directions = np.rint(np.arctan2(vectors[:, 1], vectors[:, 0]) * bins / np.pi).astype(int) % bins
        side_bins = np.repeat(directions, BOUNDARY_POINTS_PER_SIDE)
        cost[visible] = oriented[side_bins[visible], xy[visible, 1], xy[visible, 0]]
        # Penalize the worst side so a sharp front wall alone cannot win.
        sides = cost.reshape(4, -1).mean(axis=1)
        return sides.mean() + sides.max() + _score(dt, terrain, cam, pose), pose

    # Seed from the demo stand dimensions (mm), then fit distance, height and lateral offset.
    starts = [np.array([az, back, back * slope, 0.])
              for az in range(35, 146, 5) for back in (410., 430., 450.)
              for slope in (0.35, 160. / 430., 0.39)]
    best = None
    for params in sorted(starts, key=lambda p: evaluate(p)[0])[:4]:
        score, pose = evaluate(params)
        for step in (4., 2., 1., 0.5):
            for _ in range(6):
                previous = score
                for offset in np.diag([step, step * 2, step, step]):
                    for sign in (-1, 1):
                        trial = params + sign * offset
                        value, candidate = evaluate(trial)
                        if value < score:
                            params, pose, score = trial, candidate, value
                if previous == score:
                    break
        if best is None or score < best[0]:
            best = score, pose
    return best


def solve_rim_pose(frame_bgr: np.ndarray, model: TrayModel, cam: Intrinsics,
                   corners_px: np.ndarray | None = None, dt: np.ndarray | None = None,
                   facing: str | None = None) -> RimFit | None:
    """Tag-free pose: from clicked corners if given, else the detected outline snapped onto the terrain.

    facing="flood_watch" means the tray is always placed with its FLOOD WATCH edge towards the camera,
    which settles which way it faces; otherwise the terrain has to decide, and may be unsure."""
    if facing is not None and facing not in FACINGS:
        raise ValueError(f"unknown facing {facing!r}; expected one of {FACINGS} or None")
    if corners_px is not None:
        return solve_clicked_pose(frame_bgr, model, cam, corners_px)
    dt = edge_distance(frame_bgr) if dt is None else dt
    pts = _edge_points(model)
    if facing == "flood_watch":
        outline_cost, stand = _stand_fit(frame_bgr, model, cam)
        if outline_cost < 8.0:
            score = _score(dt, pts, cam, stand)
            if score <= MAX_MEAN_CHAMFER_PX:
                return RimFit(PoseFix(stand, score, (), camera_position_mm(stand)), cam, score, float("inf"), "rim")
    quads = detect_tray_quads(frame_bgr)
    candidates = []
    for quad in quads:
        for obj, img in _hypotheses(model, quad):
            ok, rvec, tvec = cv2.solvePnP(obj, img, cam.matrix, cam.dist_array, flags=cv2.SOLVEPNP_IPPE)
            if not ok:
                continue
            pose = Pose(rvec.reshape(3), tvec.reshape(3))
            if camera_position_mm(pose)[2] <= model.rim_top_mm or not _faces(model, pose, facing):
                continue  # camera below the table (mirrored) or on the wrong side for the placement rule
            candidates.append(_descend(dt, pts, cam, pose, QUICK_SCHEDULE))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[2])
    finals = sorted((_descend(dt, pts, c[1], c[0], FULL_SCHEDULE) for c in candidates[:TOP_CANDIDATES * 2]),
                    key=lambda c: c[2])
    best_pose, best_cam, best_score = finals[0]
    rivals = [c[2] for c in finals[1:] + candidates if _differs(c[0], best_pose)]
    margin = float("inf") if facing is not None or not rivals else min(rivals) / max(best_score, 1e-6)
    fix = PoseFix(best_pose, best_score, (), camera_position_mm(best_pose))
    return RimFit(fix, best_cam, best_score, margin, "rim")


def track_rim_pose(frame_bgr: np.ndarray, model: TrayModel, previous: RimFit) -> RimFit:
    """Small refinement from the previous fit (camera nudged, e.g. hover drift)."""
    dt = edge_distance(frame_bgr)
    pose, cam, score = _descend(dt, _edge_points(model), previous.cam, previous.fix.pose, TRACK_SCHEDULE)
    fix = PoseFix(pose, score, (), camera_position_mm(pose))
    return RimFit(fix, cam, score, previous.margin, previous.source)


def rim_problem(fit: RimFit | None) -> str | None:
    """Why a rim fit can't be trusted, or None."""
    if fit is None:
        return "tray not found: no tags and no clear tray outline; click the 4 tray corners (Set tray corners)"
    if fit.score_px > MAX_MEAN_CHAMFER_PX:
        return f"tray outline found but the terrain doesn't line up ({fit.score_px:.1f} px); click the 4 tray corners"
    if fit.source == "rim" and fit.margin < 1.0 / AMBIGUITY_RATIO:
        return "can't tell which way the tray faces: click the 4 tray corners (Set tray corners)"
    return None
