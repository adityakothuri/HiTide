"""Synthetic drone frames with exact ground truth, for stress tests and the offline demo.

The renderer is independent of the pipeline: it ray-casts every pixel into the terrain and the water
plane (camera.ray_to_terrain), while the pipeline goes the other way (project cells into the image).
Noise knobs model what goes wrong in the field: pose error, a biased mask boundary, flicker/glare
blobs, occluding trees and DEM errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import cv2
import numpy as np

from vision.camera import Intrinsics, Pose, ray_to_terrain
from vision.geom import densify, dist_to_polyline
from vision.grid import GroundGrid, Seg

# ADE20K ids used by the renderer (asserted against the real model's id2label in tests)
ADE = {"wall": 0, "building": 1, "sky": 2, "tree": 4, "road": 6, "grass": 9, "person": 12,
       "earth": 13, "car": 20, "water": 21}


@dataclass(frozen=True)
class Scene:
    grid: GroundGrid
    road: np.ndarray                     # (k, 2) centreline polyline, metres
    road_half_width_m: float
    wse_m: float
    trees: tuple[tuple[float, float, float], ...] = ()   # (x, y, radius) canopy discs

    def road_min_z(self, step: float = 0.25) -> float:
        pts = densify(self.road, step)
        z = self.grid.height_at(pts[:, 0], pts[:, 1])
        return float(np.nanmin(z))


@dataclass(frozen=True)
class Noise:
    boundary_px: int = 0          # +dilate / -erode the water mask (systematic segmentation bias)
    flicker_frac: float = 0.0     # fraction of pixels in random flipped blobs
    blur_px: float = 0.8          # softness of the water probability at the boundary
    pose_sigma_m: float = 0.0     # error in the pose handed to the pipeline (not the render pose)
    pose_sigma_z_m: float = 0.0
    pose_sigma_deg: float = 0.0


@dataclass(frozen=True)
class Frame:
    seg: Seg
    true_pose: Pose
    est_pose: Pose
    truth: dict = field(default_factory=dict)


def valley_scene(
    wse_above_bed_m: float = 1.2, bank_slope: float = 0.12, bed_z: float = 500.0,
    half_size_m: float = 60.0, res_m: float = 0.5, trees: tuple = (), seed: int = 0,
) -> Scene:
    """A river valley running north-south, a road crossing it east-west and dipping to the bed."""
    n = int(round(2 * half_size_m / res_m)) + 1
    xs = -half_size_m + np.arange(n) * res_m
    x, y = np.meshgrid(xs, xs)
    rng = np.random.default_rng(seed)
    z = bed_z + bank_slope * np.maximum(np.abs(x) - 3.0, 0.0) + 0.004 * y + 0.02 * np.sin(0.21 * y + rng.uniform(0, 6))
    grid = GroundGrid(float(xs[0]), float(xs[0]), res_m, z)
    road = np.array([[-half_size_m + 2, 0.0], [half_size_m - 2, 0.0]])
    return Scene(grid, road, 4.0, bed_z + wse_above_bed_m, tuple(trees))


def default_camera(width: int = 320, height: int = 240) -> Intrinsics:
    return Intrinsics.from_hfov(width, height, 82.6)       # Tello / DJI-class wide lens


def oblique_pose(scene: Scene, agl_m: float = 55.0, back_m: float = 45.0, heading_deg: float = 0.0,
                 pitch_deg: float = 52.0) -> Pose:
    z0 = float(np.nanmedian(scene.grid.z))
    rad = np.radians(heading_deg)
    return Pose(-back_m * np.sin(rad), -back_m * np.cos(rad), z0 + agl_m, heading_deg, pitch_deg)


def render(scene: Scene, cam: Intrinsics, pose: Pose) -> tuple[np.ndarray, np.ndarray]:
    """Clean labels (h, w) and the label underneath any water (for boundary-bias noise)."""
    h, w = cam.height, cam.width
    vv, uu = np.mgrid[0:h, 0:w]
    uv = np.column_stack([uu.ravel() + 0.5, vv.ravel() + 0.5])
    t_max = 6 * (pose.z - float(np.nanmin(scene.grid.z)) + 1)
    pts, hit = ray_to_terrain(cam, pose, uv, scene.grid.height_at, t_max)
    labels = np.full(len(uv), ADE["sky"], dtype=np.int16)
    under = labels.copy()
    g = pts[hit]
    on_road = dist_to_polyline(g[:, :2], scene.road) <= scene.road_half_width_m
    base = np.where(on_road, ADE["road"], ADE["grass"]).astype(np.int16)
    # the ray crosses the water plane before the terrain when the terrain hit is below it
    wet = g[:, 2] < scene.wse_m
    surf_xy = g[:, :2].copy()
    if wet.any():
        d = g[wet] - np.array([pose.x, pose.y, pose.z])
        t = (scene.wse_m - pose.z) / d[:, 2]
        surf_xy[wet] = np.array([pose.x, pose.y]) + t[:, None] * d[:, :2]
    lab = np.where(wet, ADE["water"], base)
    for tx, ty, tr in scene.trees:
        canopy = np.hypot(surf_xy[:, 0] - tx, surf_xy[:, 1] - ty) <= tr
        lab = np.where(canopy, ADE["tree"], lab)
        base = np.where(canopy, ADE["tree"], base)
    labels[hit] = lab
    under[hit] = base
    return labels.reshape(h, w), under.reshape(h, w)


def apply_noise(labels: np.ndarray, under: np.ndarray, noise: Noise, rng: np.random.Generator,
                low_light: bool = False) -> Seg:
    water = (labels == ADE["water"]).astype(np.uint8)
    if noise.boundary_px:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * abs(noise.boundary_px) + 1,) * 2)
        water = cv2.dilate(water, k) if noise.boundary_px > 0 else cv2.erode(water, k)
    if noise.flicker_frac > 0:
        h, w = water.shape
        n_blobs = max(1, int(noise.flicker_frac * h * w / 12))
        for _ in range(n_blobs):
            cy, cx, r = rng.integers(0, h), rng.integers(0, w), int(rng.integers(1, 3))
            water[max(0, cy - r):cy + r, max(0, cx - r):cx + r] ^= 1
    out_labels = np.where(water == 1, ADE["water"], np.where(labels == ADE["water"], under, labels))
    out_labels = np.where(labels == ADE["sky"], ADE["sky"], out_labels).astype(np.int16)
    p = water.astype(np.float32)
    if noise.blur_px > 0:
        p = cv2.GaussianBlur(p, (0, 0), noise.blur_px)
    return Seg(out_labels, np.clip(p, 0, 1), low_light)


def make_frame(scene: Scene, cam: Intrinsics, pose: Pose, noise: Noise = Noise(), seed: int = 0,
               rendered: tuple[np.ndarray, np.ndarray] | None = None, est_base: Pose | None = None) -> Frame:
    """est_base: a biased pose shared by every frame of a hover (GPS/gimbal bias); noise adds jitter on top."""
    rng = np.random.default_rng(seed)
    labels, under = rendered if rendered is not None else render(scene, cam, pose)
    seg = apply_noise(labels, under, noise, rng)
    est = (est_base or pose).perturbed(rng, noise.pose_sigma_m, noise.pose_sigma_deg, noise.pose_sigma_z_m)
    truth = {"wse_m": scene.wse_m, "road_min_z": scene.road_min_z(),
             "depth_at_road_in": max(0.0, scene.wse_m - scene.road_min_z()) / 0.0254}
    return Frame(seg, pose, est, truth)


def with_wse(scene: Scene, wse_m: float) -> Scene:
    return replace(scene, wse_m=wse_m)
