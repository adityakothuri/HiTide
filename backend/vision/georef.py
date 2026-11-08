"""Georeference a real video frame: recover the camera pose so the water-level model can run on footage
that was not shot by our drone.

Two tools:
- fit_pose: camera position known (e.g. the filmer published coordinates), orientation + field of view
  unknown. Image points that lie on a mapped line (a trail edge, a curb) are back-projected onto the
  terrain and pulled onto that line; priors keep the fit physical. Returns the pose, intrinsics and an
  honest uncertainty (from the Jacobian), which feeds the model's range.
- rotation tracking: a hand-held camera mostly ROTATES, so frame-to-frame motion is a homography
  H = K R K^-1 regardless of depth; R updates the pose without re-picking points.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from vision.camera import Intrinsics, Pose, rays, rotation


def pose_from_rotation(r_wc: np.ndarray, x: float, y: float, z: float) -> Pose:
    """Inverse of camera.rotation: world->camera matrix (rows right, down, forward) -> heading/pitch/roll."""
    fwd = r_wc[2] / np.linalg.norm(r_wc[2])
    heading = math.degrees(math.atan2(fwd[0], fwd[1]))
    pitch = math.degrees(-math.asin(float(np.clip(fwd[2], -1.0, 1.0))))
    h = math.radians(heading)
    right0 = np.array([math.cos(h), -math.sin(h), 0.0])
    down0 = np.cross(fwd, right0)
    roll = math.degrees(math.atan2(float(r_wc[0] @ down0), float(r_wc[0] @ right0)))
    return Pose(x, y, z, heading % 360.0, pitch, roll)


def rotate_pose(pose: Pose, r_rel: np.ndarray) -> Pose:
    """New pose after the camera rotates by r_rel (key-camera coords -> new-camera coords)."""
    return pose_from_rotation(r_rel @ rotation(pose), pose.x, pose.y, pose.z)


def k_matrix(cam: Intrinsics) -> np.ndarray:
    return np.array([[cam.fx, 0, cam.cx], [0, cam.fy, cam.cy], [0, 0, 1.0]])


def rotation_from_homography(h: np.ndarray, cam: Intrinsics) -> np.ndarray:
    """Pure-rotation homography -> nearest proper rotation matrix (SVD projection)."""
    k = k_matrix(cam)
    m = np.linalg.inv(k) @ h @ k
    u, _, vt = np.linalg.svd(m)
    r = u @ vt
    return r if np.linalg.det(r) > 0 else -r


def track_rotation(prev_gray: np.ndarray, gray: np.ndarray, cam: Intrinsics,
                   mask: np.ndarray | None = None) -> tuple[np.ndarray | None, int]:
    """Rotation between two frames from tracked corners on static parts (mask=True where usable)."""
    import cv2

    m = None if mask is None else mask.astype(np.uint8) * 255
    p0 = cv2.goodFeaturesToTrack(prev_gray, 400, 0.01, 8, mask=m)
    if p0 is None or len(p0) < 12:
        return None, 0
    p1, st, _ = cv2.calcOpticalFlowPyrLK(prev_gray, gray, p0, None)
    back, st2, _ = cv2.calcOpticalFlowPyrLK(gray, prev_gray, p1, None)
    ok = (st[:, 0] == 1) & (st2[:, 0] == 1) & (np.linalg.norm((back - p0)[:, 0], axis=1) < 1.0)
    if ok.sum() < 12:
        return None, int(ok.sum())
    h, inl = cv2.findHomography(p0[ok], p1[ok], cv2.RANSAC, 2.0)
    if h is None:
        return None, 0
    return rotation_from_homography(h, cam), int(inl.sum())


@dataclass(frozen=True)
class Priors:
    """Gaussian priors (mean, sigma). Angles in degrees, distances in metres."""
    heading: tuple[float, float]
    pitch: tuple[float, float]
    roll: tuple[float, float] = (0.0, 3.0)
    hfov: tuple[float, float] = (66.0, 6.0)
    eye_m: tuple[float, float] = (1.5, 0.7)        # camera height above the ground at its position
    dx: tuple[float, float] = (0.0, 4.0)           # camera position error (published coordinates)
    dy: tuple[float, float] = (0.0, 4.0)


@dataclass(frozen=True)
class PoseFit:
    pose: Pose
    cam: Intrinsics
    rms_m: float                  # mean ground miss of the constraint points (m)
    rms_px: float                 # image misfit of the constraint points (px)
    sigma_deg: float              # 1-sigma attitude uncertainty (max of heading/pitch/roll)
    sigma_m: float                # 1-sigma horizontal position uncertainty
    sigma_z_m: float
    sigma_pitch_deg: float = 0.0  # the attitude term that moves points along the view (what matters for level)


def _dist_to_polyline(p: np.ndarray, line: np.ndarray) -> np.ndarray:
    a, b = line[:-1], line[1:]
    ab = b - a
    t = np.clip(np.einsum("nkd,kd->nk", p[:, None, :] - a[None], ab) / np.maximum((ab**2).sum(1), 1e-12), 0, 1)
    proj = a[None] + t[..., None] * ab[None]
    return np.min(np.linalg.norm(p[:, None, :] - proj, axis=2), axis=1)


def _plane_hit(cam: Intrinsics, pose: Pose, uv: np.ndarray, z: np.ndarray) -> np.ndarray:
    d = rays(cam, pose, uv)
    t = (z - pose.z) / np.where(np.abs(d[:, 2]) < 1e-9, -1e-9, d[:, 2])
    t = np.where(t > 0, t, 1e4)
    return np.array([pose.x, pose.y])[None] + t[:, None] * d[:, :2]


def _hit(cam: Intrinsics, pose: Pose, uv: np.ndarray, line_z) -> np.ndarray:
    """Ground hit of each ray: on a plane z = line_z, or on terrain if line_z is height_at(x, y) (2 passes)."""
    if not callable(line_z):
        return _plane_hit(cam, pose, uv, np.full(len(uv), float(line_z)))
    z = np.full(len(uv), float(np.nanmedian(line_z(np.array([pose.x]), np.array([pose.y])))) - 3.0)
    for _ in range(3):
        xy = _plane_hit(cam, pose, uv, z)
        zz = line_z(xy[:, 0], xy[:, 1])
        z = np.where(np.isfinite(zz), zz, z)
    return _plane_hit(cam, pose, uv, z)


def fit_pose(uv, line_xy, line_z, size: tuple[int, int], cam_xy: tuple[float, float],
             ground_z: float, priors: Priors, px_sigma: float = 3.0) -> PoseFit:
    """Fit orientation, field of view, eye height and a small position error.

    uv / line_xy: one array each, or lists of them (several mapped lines, e.g. both edges of a trail).
    line_z: a constant height, or height_at(x, y) to read heights from the terrain.
    Residuals: image row of the projected line minus each picked row (px), plus Gaussian priors.
    """
    from scipy.optimize import least_squares

    w, h = size
    names = ("heading", "pitch", "roll", "hfov", "eye_m", "dx", "dy")
    mu = np.array([getattr(priors, n)[0] for n in names])
    sd = np.array([getattr(priors, n)[1] for n in names])

    def build(p):
        cam = Intrinsics.from_hfov(w, h, float(np.clip(p[3], 20, 120)))
        pose = Pose(cam_xy[0] + p[5], cam_xy[1] + p[6], ground_z + p[4], p[0], p[1], p[2])
        return cam, pose

    from vision.camera import project
    from vision.geom import densify

    uvs = [np.asarray(u, float) for u in (uv if isinstance(uv, (list, tuple)) else [uv])]
    lines = [np.asarray(ln, float) for ln in (line_xy if isinstance(line_xy, (list, tuple)) else [line_xy])]
    worlds = []
    for ln in lines:
        pts = densify(ln, 0.5)
        zs = line_z(pts[:, 0], pts[:, 1]) if callable(line_z) else np.full(len(pts), float(line_z))
        ok = np.isfinite(zs)
        worlds.append(np.column_stack([pts[ok], zs[ok]]))

    def misfit(cam, pose):
        out = []
        for u_pick, world in zip(uvs, worlds):
            uvl, dep = project(cam, pose, world)
            good = (dep > 0.5) & np.isfinite(uvl).all(axis=1)
            if good.sum() < 2:
                out.append(np.full(len(u_pick), 300.0))
                continue
            order = np.argsort(uvl[good, 0])
            u, v = uvl[good, 0][order], uvl[good, 1][order]
            inside = (u_pick[:, 0] >= u[0]) & (u_pick[:, 0] <= u[-1])
            out.append(np.where(inside, np.interp(u_pick[:, 0], u, v) - u_pick[:, 1], 300.0))
        return np.clip(np.concatenate(out), -300, 300)

    def resid(p):
        cam, pose = build(p)
        return np.concatenate([misfit(cam, pose) / px_sigma, (p - mu) / sd])

    sol = least_squares(resid, mu.copy(), method="trf", x_scale=sd)
    cam, pose = build(sol.x)
    hit = _hit(cam, pose, uvs[0], line_z)
    rms = float(np.sqrt(np.mean(_dist_to_polyline(hit, lines[0]) ** 2)))
    px_rms = float(np.sqrt(np.mean(misfit(cam, pose) ** 2)))
    try:
        cov = np.linalg.inv(sol.jac.T @ sol.jac)
        s = np.sqrt(np.clip(np.diag(cov), 0, None))
    except np.linalg.LinAlgError:
        s = sd
    return PoseFit(pose, cam, rms, px_rms, float(max(s[0], s[1], s[2])), float(np.hypot(s[5], s[6])), float(s[4]),
                   float(s[1]))


def with_pose(fit: PoseFit, pose: Pose) -> PoseFit:
    return replace(fit, pose=pose)
