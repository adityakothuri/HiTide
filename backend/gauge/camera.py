"""Pinhole camera model and projection helpers (OpenCV convention: tray mm -> camera)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

CAMERA_JSON_ENV = "GAUGE_CAMERA_JSON"
DEFAULT_CAMERA_JSON = Path.home() / "tello-test" / "gauge_camera.json"
TELLO_WIDTH, TELLO_HEIGHT = 960, 720
TELLO_DIAGONAL_FOV_DEG = 82.6  # DJI spec; gives fx about 683 px at 960x720
MIN_DEPTH_MM = 1.0


@dataclass(frozen=True)
class Intrinsics:
    fx: float
    fy: float
    cx: float
    cy: float
    dist: tuple[float, ...] = (0.0, 0.0, 0.0, 0.0, 0.0)

    @property
    def matrix(self) -> np.ndarray:
        return np.array([[self.fx, 0.0, self.cx], [0.0, self.fy, self.cy], [0.0, 0.0, 1.0]])

    @property
    def dist_array(self) -> np.ndarray:
        return np.asarray(self.dist, dtype=np.float64)

    @property
    def has_distortion(self) -> bool:
        return any(abs(v) > 0.0 for v in self.dist)


@dataclass(frozen=True, eq=False)
class Pose:
    """Rodrigues rotation and translation taking tray mm into the camera frame."""

    rvec: np.ndarray
    tvec: np.ndarray

    @property
    def rotation(self) -> np.ndarray:
        return cv2.Rodrigues(np.asarray(self.rvec, dtype=np.float64).reshape(3))[0]


def tello_default(width: int = TELLO_WIDTH, height: int = TELLO_HEIGHT) -> Intrinsics:
    """Default Tello intrinsics: f from the 82.6 deg diagonal FOV (about 683 px at 960x720)."""
    focal = 0.5 * float(np.hypot(width, height)) / float(np.tan(np.radians(TELLO_DIAGONAL_FOV_DEG) / 2.0))
    return Intrinsics(focal, focal, width / 2.0, height / 2.0)


def load_intrinsics(path: str | Path | None = None, width: int = TELLO_WIDTH,
                    height: int = TELLO_HEIGHT) -> Intrinsics:
    """Load a saved calibration (``GAUGE_CAMERA_JSON`` or ``~/tello-test/gauge_camera.json``) or default."""
    env = os.environ.get(CAMERA_JSON_ENV)
    candidate = Path(path) if path else (Path(env) if env else DEFAULT_CAMERA_JSON)
    if not candidate.is_file():
        return tello_default(width, height)
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
        fx = float(data["fx"])
        fy = float(data.get("fy", fx))
        dist = tuple(float(v) for v in data.get("dist", (0.0,) * 5))
        return Intrinsics(fx, fy, float(data.get("cx", width / 2.0)), float(data.get("cy", height / 2.0)), dist)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        logger.warning("ignoring bad camera file %s: %s", candidate, exc)
        return tello_default(width, height)


def project(points_mm: np.ndarray, cam: Intrinsics, pose: Pose) -> tuple[np.ndarray, np.ndarray]:
    """Project (N,3) tray points. Returns pixels (N,2) and depth along the optical axis (N,).

    Points behind the camera get NaN pixels.
    """
    pts = np.asarray(points_mm, dtype=np.float64).reshape(-1, 3)
    tvec = np.asarray(pose.tvec, dtype=np.float64).reshape(3)
    cam_pts = pts @ pose.rotation.T + tvec
    depth = cam_pts[:, 2]
    if cam.has_distortion:
        px = cv2.projectPoints(pts, np.asarray(pose.rvec, dtype=np.float64).reshape(3, 1),
                               tvec.reshape(3, 1), cam.matrix, cam.dist_array)[0].reshape(-1, 2)
    else:
        safe = np.where(depth > MIN_DEPTH_MM, depth, np.nan)
        px = np.stack([cam.fx * cam_pts[:, 0] / safe + cam.cx,
                       cam.fy * cam_pts[:, 1] / safe + cam.cy], axis=1)
    px = np.where((depth > MIN_DEPTH_MM)[:, None], px, np.nan)
    return px, depth


def camera_position_mm(pose: Pose) -> np.ndarray:
    """Camera centre in tray coordinates."""
    return -pose.rotation.T @ np.asarray(pose.tvec, dtype=np.float64).reshape(3)
