"""ArUco tag detection and camera pose from the four tray tags."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np

from .camera import Intrinsics, Pose, camera_position_mm, project
from .model import TrayModel

logger = logging.getLogger(__name__)

MIN_TAGS = 3
MAX_REPROJ_PX = 4.0
MIN_FOCAL_PX, MAX_FOCAL_PX = 200.0, 3000.0
MIN_TILT_CONDITION = 0.06
MIN_MARKER_PERIMETER_RATE = 0.01
THRESH_WIN_MAX, THRESH_WIN_STEP = 53, 6


@dataclass(frozen=True, eq=False)
class PoseFix:
    pose: Pose
    reproj_err_px: float
    tag_ids: tuple[int, ...]
    camera_mm: np.ndarray


def _dictionary(name: str) -> "cv2.aruco.Dictionary":
    if not hasattr(cv2.aruco, name):
        raise ValueError(f"unknown ArUco dictionary {name!r}")
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name))


@lru_cache(maxsize=4)
def _detector(name: str) -> "cv2.aruco.ArucoDetector":
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    params.minMarkerPerimeterRate = MIN_MARKER_PERIMETER_RATE
    params.adaptiveThreshWinSizeMax = THRESH_WIN_MAX
    params.adaptiveThreshWinSizeStep = THRESH_WIN_STEP
    return cv2.aruco.ArucoDetector(_dictionary(name), params)


def _gray(frame: np.ndarray) -> np.ndarray:
    return frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def detect_tags(frame_bgr: np.ndarray, dictionary: str = "DICT_4X4_50") -> dict[int, np.ndarray]:
    """Detect markers; returns ``{id: (4,2) corners TL,TR,BR,BL}`` (float64 px)."""
    if frame_bgr is None or frame_bgr.size == 0:
        return {}
    corners, ids, _ = _detector(dictionary).detectMarkers(np.ascontiguousarray(_gray(frame_bgr)))
    if ids is None:
        return {}
    return {int(i): np.asarray(c, dtype=np.float64).reshape(4, 2) for i, c in zip(ids.ravel(), corners)}


def _quad_centre(quad: np.ndarray) -> np.ndarray:
    """Projected centre of a quad: intersection of its diagonals."""
    p0, p1, p2, p3 = quad
    a = np.stack([p2 - p0, -(p3 - p1)], axis=1)
    try:
        s = np.linalg.solve(a, p1 - p0)
    except np.linalg.LinAlgError:
        return quad.mean(axis=0)
    return p0 + s[0] * (p2 - p0)


def _corner_error(obj: np.ndarray, img: np.ndarray, cam: Intrinsics, pose: Pose) -> float:
    px, depth = project(obj, cam, pose)
    if np.any(depth <= 0) or not np.all(np.isfinite(px)):
        return float("inf")
    return float(np.sqrt(np.mean(np.sum((px - img) ** 2, axis=1))))


def _solve_planar(obj: np.ndarray, img: np.ndarray, cam: Intrinsics, flag: int = cv2.SOLVEPNP_IPPE) -> Pose | None:
    try:
        ok, rvec, tvec = cv2.solvePnP(obj, img, cam.matrix, cam.dist_array, flags=flag)
    except cv2.error as exc:
        logger.debug("IPPE failed: %s", exc)
        return None
    return Pose(rvec.reshape(3), tvec.reshape(3)) if ok else None


def _refine(obj: np.ndarray, img: np.ndarray, cam: Intrinsics, pose: Pose) -> Pose | None:
    try:
        rvec, tvec = cv2.solvePnPRefineLM(obj, img, cam.matrix, cam.dist_array,
                                          pose.rvec.reshape(3, 1).copy(), pose.tvec.reshape(3, 1).copy())
    except cv2.error as exc:
        logger.debug("LM refine failed: %s", exc)
        return None
    return Pose(rvec.reshape(3), tvec.reshape(3))


def _centre_candidate(ids: tuple[int, ...], seen: dict[int, np.ndarray], model: TrayModel,
                      cam: Intrinsics) -> Pose | None:
    """IPPE on tag centres (needs 4 coplanar points); robust to a rotated sticker."""
    if len(ids) < 4:
        return None
    obj = np.stack([model.tag_corners_mm[i].mean(axis=0) for i in ids])
    img = np.stack([_quad_centre(np.asarray(seen[i], dtype=np.float64)) for i in ids])
    return _solve_planar(obj, img, cam)


def solve_pose(seen: dict[int, np.ndarray], model: TrayModel, cam: Intrinsics) -> PoseFix | None:
    """Camera pose from detected tags (>= 3 known ids). None when it cannot be trusted."""
    ids = tuple(sorted(i for i in seen if i in model.tag_corners_mm))
    if len(ids) < MIN_TAGS:
        return None
    obj = np.concatenate([model.tag_corners_mm[i] for i in ids]).astype(np.float64)
    img = np.concatenate([np.asarray(seen[i], dtype=np.float64).reshape(4, 2) for i in ids])
    starts = [p for p in (_centre_candidate(ids, seen, model, cam), _solve_planar(obj, img, cam, cv2.SOLVEPNP_SQPNP))
              if p is not None]
    refined = [r for r in (_refine(obj, img, cam, p) for p in starts) if r is not None]
    scored = [(_corner_error(obj, img, cam, p), p) for p in starts + refined]
    scored = [s for s in scored if np.isfinite(s[0]) and camera_position_mm(s[1])[2] > 0.0]
    if not scored:
        return None
    err, best = min(scored, key=lambda s: s[0])
    if err > MAX_REPROJ_PX:
        logger.debug("pose rejected, reprojection error %.2f px", err)
        return None
    return PoseFix(best, err, ids, camera_position_mm(best))


def estimate_focal(seen: dict[int, np.ndarray], model: TrayModel, width: int, height: int) -> float | None:
    """Focal length (px) from the tag-plane homography with the principal point at the image centre.

    Returns None when the view is (near) fronto-parallel or the tags are too few: the constraint
    is ill-conditioned there.
    """
    ids = [i for i in sorted(seen) if i in model.tag_corners_mm]
    if len(ids) < MIN_TAGS:
        return None
    obj = np.concatenate([model.tag_corners_mm[i][:, :2] for i in ids]).astype(np.float64)
    img = np.concatenate([np.asarray(seen[i], dtype=np.float64).reshape(4, 2) for i in ids])
    h_mat, _ = cv2.findHomography(obj, img, 0)
    if h_mat is None or not np.all(np.isfinite(h_mat)):
        return None
    shift = np.array([[1.0, 0.0, -width / 2.0], [0.0, 1.0, -height / 2.0], [0.0, 0.0, 1.0]])
    h = shift @ h_mat
    h = h / np.linalg.norm(h[:, 0])
    h1, h2 = h[:, 0], h[:, 1]
    # r1.r2 = 0 and |r1| = |r2| both read  u * b_k + a_k = 0  with u = 1 / f^2
    a = np.array([h1[2] * h2[2], h1[2] ** 2 - h2[2] ** 2])
    b = np.array([h1[0] * h2[0] + h1[1] * h2[1], h1[0] ** 2 + h1[1] ** 2 - h2[0] ** 2 - h2[1] ** 2])
    denom = float(b @ b)
    if denom <= 0.0:
        return None
    u = -float(a @ b) / denom
    if not np.isfinite(u) or u <= 0.0:
        return None
    focal = 1.0 / np.sqrt(u)
    condition = float(np.linalg.norm(a)) * focal ** 2  # grows with plane tilt, ~0 when fronto-parallel
    if condition < MIN_TILT_CONDITION or not (MIN_FOCAL_PX <= focal <= MAX_FOCAL_PX):
        return None
    return float(focal)
