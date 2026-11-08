"""Camera pose from ArUco tags at known CAD positions (the tabletop model has no GPS, the CAD gives the truth).

Tags lie flat on the tray's corner pads. Detected pixel corners + CAD corners -> cv2.solvePnP -> a vision Pose
in the same frame as the corner coordinates (whatever units they are in; the pipeline uses the "ex" frame).
"""

from __future__ import annotations

import math
from typing import Mapping

import cv2
import numpy as np

from vision.camera import Intrinsics, Pose

MIN_FWD_XY = 1e-12
MIN_TAGS = 2                  # one 20 mm tag has an IPPE ambiguity and a poor attitude
MAX_RMS_PX = 1.5              # reject a pose whose tag corners reproject worse than this
CV_TO_PIPELINE_PX = 0.5       # OpenCV puts pixel centres at integers; Intrinsics/grid use index + 0.5


def pose_from_rotation(r: np.ndarray, c: np.ndarray) -> Pose:
    """Inverse of camera.rotation: world->camera rotation (rows right, down, forward) + centre -> Pose."""
    fwd = r[2]
    pitch = math.asin(float(np.clip(-fwd[2], -1.0, 1.0)))
    if math.hypot(fwd[0], fwd[1]) > MIN_FWD_XY:
        heading = math.atan2(fwd[0], fwd[1])
        right0 = np.array([math.cos(heading), -math.sin(heading), 0.0])
        down0 = np.cross(fwd, right0)
        roll = math.atan2(float(r[0] @ down0), float(r[0] @ right0))
    else:                                    # straight down: heading and roll are the same rotation
        heading, roll = math.atan2(-r[0][1], r[0][0]), 0.0
    return Pose(float(c[0]), float(c[1]), float(c[2]), math.degrees(heading) % 360.0, math.degrees(pitch),
                math.degrees(roll))


def _matrix(cam: Intrinsics) -> np.ndarray:
    return np.array([[cam.fx, 0, cam.cx], [0, cam.fy, cam.cy], [0, 0, 1]], dtype=float)


def solve_pose(seen: Mapping[int, np.ndarray], tags: Mapping[int, np.ndarray], cam: Intrinsics,
               dist: np.ndarray | None = None, min_tags: int = MIN_TAGS, max_rms_px: float = MAX_RMS_PX) -> Pose | None:
    """Pose from every tag that is both detected and known. None if too few tags, PnP fails, or the corners
    reproject worse than max_rms_px (a misplaced/rotated tag or a false detection)."""
    ids = [i for i in seen if i in tags]
    if len(ids) < max(1, min_tags):
        return None
    obj = np.concatenate([np.asarray(tags[i], dtype=float).reshape(4, 3) for i in ids])
    img = np.concatenate([np.asarray(seen[i], dtype=float).reshape(4, 2) for i in ids])
    k, d = _matrix(cam), np.zeros(5) if dist is None else np.asarray(dist, dtype=float)
    planar = np.ptp(obj[:, 2]) < 1e-9
    ok, rvec, tvec = cv2.solvePnP(obj, img, k, d, flags=cv2.SOLVEPNP_IPPE if planar else cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        return None
    ok, rvec, tvec = cv2.solvePnP(obj, img, k, d, rvec, tvec, useExtrinsicGuess=True, flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        return None
    proj, _ = cv2.projectPoints(obj, rvec, tvec, k, d)
    rms = float(np.sqrt(np.mean(np.sum((proj.reshape(-1, 2) - img) ** 2, axis=1))))
    if rms > max_rms_px:
        return None
    r, _ = cv2.Rodrigues(rvec)
    return pose_from_rotation(r, (-r.T @ tvec).ravel())


def detect_tags(frame_bgr: np.ndarray, dictionary: str) -> dict[int, np.ndarray]:
    """ArUco corners per tag id, (4, 2) pixels in TL, TR, BR, BL order (sub-pixel refined, pipeline convention)."""
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary))
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    corners, ids, _ = cv2.aruco.ArucoDetector(d, params).detectMarkers(frame_bgr)
    if ids is None:
        return {}
    return {int(i): c.reshape(4, 2).astype(float) + CV_TO_PIPELINE_PX for i, c in zip(ids.ravel(), corners)}
