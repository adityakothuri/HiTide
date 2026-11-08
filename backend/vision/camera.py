"""Pinhole camera + drone pose in local ENU metres (x east, y north, z up).

Pose convention: heading_deg clockwise from north, pitch_deg = gimbal angle below the horizon
(90 = straight down), roll_deg about the optical axis. OpenCV camera frame: x right, y down, z forward.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np


@dataclass(frozen=True)
class Intrinsics:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int

    @staticmethod
    def from_hfov(width: int, height: int, hfov_deg: float) -> "Intrinsics":
        f = (width / 2) / math.tan(math.radians(hfov_deg) / 2)
        return Intrinsics(f, f, width / 2, height / 2, width, height)

    def scaled(self, width: int, height: int) -> "Intrinsics":
        sx, sy = width / self.width, height / self.height
        return Intrinsics(self.fx * sx, self.fy * sy, self.cx * sx, self.cy * sy, width, height)


@dataclass(frozen=True)
class Pose:
    x: float
    y: float
    z: float
    heading_deg: float
    pitch_deg: float
    roll_deg: float = 0.0

    def perturbed(self, rng: np.random.Generator, sigma_m: float, sigma_deg: float, sigma_z_m: float) -> "Pose":
        return replace(
            self,
            x=self.x + rng.normal(0, sigma_m),
            y=self.y + rng.normal(0, sigma_m),
            z=self.z + rng.normal(0, sigma_z_m),
            heading_deg=self.heading_deg + rng.normal(0, sigma_deg),
            pitch_deg=self.pitch_deg + rng.normal(0, sigma_deg),
            roll_deg=self.roll_deg + rng.normal(0, sigma_deg),
        )


def rotation(pose: Pose) -> np.ndarray:
    """World->camera rotation; rows are the camera right, down and forward axes in world coordinates."""
    h, p = math.radians(pose.heading_deg), math.radians(pose.pitch_deg)
    fwd = np.array([math.sin(h) * math.cos(p), math.cos(h) * math.cos(p), -math.sin(p)])
    right = np.array([math.cos(h), -math.sin(h), 0.0])
    down = np.cross(fwd, right)
    r = math.radians(pose.roll_deg)
    right_r = math.cos(r) * right + math.sin(r) * down
    down_r = -math.sin(r) * right + math.cos(r) * down
    return np.vstack([right_r, down_r, fwd])


def centre(pose: Pose) -> np.ndarray:
    return np.array([pose.x, pose.y, pose.z])


def project(cam: Intrinsics, pose: Pose, xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """World points (n, 3) -> pixel coords (n, 2) and depth along the optical axis (n,). Depth <= 0 is behind."""
    pc = (np.asarray(xyz, dtype=float) - centre(pose)) @ rotation(pose).T
    depth = pc[:, 2]
    safe = np.where(depth > 1e-9, depth, np.nan)
    u = cam.fx * pc[:, 0] / safe + cam.cx
    v = cam.fy * pc[:, 1] / safe + cam.cy
    return np.column_stack([u, v]), depth


def rays(cam: Intrinsics, pose: Pose, uv: np.ndarray) -> np.ndarray:
    """Unit world-frame ray directions (n, 3) through pixel coords (n, 2)."""
    uv = np.asarray(uv, dtype=float).reshape(-1, 2)
    d_cam = np.column_stack([(uv[:, 0] - cam.cx) / cam.fx, (uv[:, 1] - cam.cy) / cam.fy, np.ones(len(uv))])
    d = d_cam @ rotation(pose)
    return d / np.linalg.norm(d, axis=1, keepdims=True)


def ray_to_plane(cam: Intrinsics, pose: Pose, uv: np.ndarray, z: float) -> np.ndarray:
    """Where pixel rays hit the horizontal plane at height z (n, 3). NaN rows if the ray never reaches it."""
    d = rays(cam, pose, uv)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (z - pose.z) / d[:, 2]
    t = np.where(np.isfinite(t) & (t > 0), t, np.nan)
    return centre(pose) + t[:, None] * d


def ray_to_terrain(
    cam: Intrinsics, pose: Pose, uv: np.ndarray, height_at, t_max: float, steps: int = 96, refine: int = 14
) -> tuple[np.ndarray, np.ndarray]:
    """First terrain hit along each pixel ray. height_at(x, y) -> z (vectorized).

    Coarse march to bracket the first crossing, then bisection. Returns (points (n,3), hit mask (n,)).
    """
    o, d = centre(pose), rays(cam, pose, uv)
    n = len(d)
    ts = np.linspace(0.0, t_max, steps)
    prev_t, hit_t = np.zeros(n), np.full(n, np.nan)
    for t in ts[1:]:
        p = o + t * d
        below = (p[:, 2] <= height_at(p[:, 0], p[:, 1])) & np.isnan(hit_t)
        hit_t[below] = t
        if not np.isnan(hit_t).any():
            break
        prev_t = np.where(np.isnan(hit_t), t, prev_t)
    hit = ~np.isnan(hit_t)
    lo, hi = prev_t[hit], hit_t[hit]
    dh = d[hit]
    for _ in range(refine):
        mid = (lo + hi) / 2
        p = o + mid[:, None] * dh
        below = p[:, 2] <= height_at(p[:, 0], p[:, 1])
        hi = np.where(below, mid, hi)
        lo = np.where(below, lo, mid)
    pts = np.full((n, 3), np.nan)
    pts[hit] = o + ((lo + hi) / 2)[:, None] * dh
    return pts, hit
