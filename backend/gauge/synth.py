"""Synthetic renderer for the gauge tray: test rig and offline demo.

Independent of the estimator (``water.py``): it ray-casts into the truth heightfield and a flat
water plane, draws the real ArUco marker images on the pads, and degrades the frame with
configurable noise. Only ``model`` and ``camera`` are shared.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

from .camera import Intrinsics, Pose, camera_position_mm
from .model import TrayModel

logger = logging.getLogger(__name__)

RENDER_SCALE = 0.5            # terrain is ray-marched at this fraction of the output size
MARCH_STEP_MM = 0.5
BISECT_ITERS = 7
TOP_MARGIN_MM = 1.0
LIGHT_DIR = np.array([0.35, -0.45, 0.82]) / np.linalg.norm([0.35, -0.45, 0.82])
AMBIENT, DIFFUSE = 0.45, 0.65
SIDE_WALL_DARKEN = 0.7
DEPTH_REF_MM = 6.0            # water depth at which the dye alpha has roughly doubled
WET_EPS_MM = 1e-3
SKY_BGR = np.array([238.0, 228.0, 218.0])
SPEC_POWER, SPEC_GAIN = 160.0, 200.0
TABLE_BGR = np.array([128.0, 156.0, 182.0])
FAR_BGR = np.array([70.0, 70.0, 70.0])
MARKER_PX = 48
TAG_MARGIN_MM = 1.0
TAG_SHADE = 0.94
PAPER_BGR = np.array([238.0, 240.0, 240.0])
MAX_ELEVATION_DEG = 89.0
DEFAULT_TARGET_Z_MM = 10.0
DEFAULT_FILAMENT_BGR = (150, 165, 175)
DEFAULT_DYE_BGR = (190, 80, 25)
DEFAULT_DYE_ALPHA = 0.55
GLARE_RADIUS_RANGE_PX = (18, 55)
GLARE_GAIN_RANGE = (90, 190)


@dataclass(frozen=True)
class Noise:
    """Image degradations. All-zero/neutral by default."""

    blur_px: float = 0.0
    gauss_sigma: float = 0.0
    jpeg_quality: int = 0          # 0 disables JPEG
    brightness: float = 1.0
    glare_blobs: int = 0
    pose_jitter_deg: float = 0.0

    @classmethod
    def modest(cls) -> "Noise":
        """A believable Tello frame: slight blur, sensor noise, JPEG, tiny pose wobble."""
        return cls(blur_px=0.8, gauss_sigma=2.5, jpeg_quality=75, brightness=1.0,
                   glare_blobs=0, pose_jitter_deg=0.0)


def look_at_pose(model: TrayModel, distance_mm: float, elevation_deg: float, azimuth_deg: float,
                 target_mm: tuple[float, float, float] | np.ndarray | None = None,
                 roll_deg: float = 0.0) -> Pose:
    """Camera ``distance_mm`` from ``target_mm`` (default tray centre) looking at it."""
    if target_mm is None:
        target = np.array([model.size_mm[0] / 2.0, model.size_mm[1] / 2.0, DEFAULT_TARGET_Z_MM])
    else:
        target = np.asarray(target_mm, dtype=np.float64).reshape(3)
    el = np.radians(min(float(elevation_deg), MAX_ELEVATION_DEG))
    az = np.radians(float(azimuth_deg))
    position = target + distance_mm * np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
    forward = (target - position) / np.linalg.norm(target - position)
    right = np.cross(forward, [0.0, 0.0, 1.0])
    right /= np.linalg.norm(right)
    down = np.cross(forward, right)
    roll = np.radians(roll_deg)
    right, down = (np.cos(roll) * right + np.sin(roll) * down, -np.sin(roll) * right + np.cos(roll) * down)
    rot = np.stack([right, down, forward])
    return Pose(cv2.Rodrigues(rot)[0].reshape(3), (-rot @ position).reshape(3))


def _smooth_noise(rng: np.random.Generator, shape: tuple[int, int], cell: int) -> np.ndarray:
    small = rng.standard_normal((max(2, shape[0] // cell + 2), max(2, shape[1] // cell + 2))).astype(np.float32)
    return cv2.resize(small, (shape[1], shape[0]), interpolation=cv2.INTER_CUBIC)


def _cell_colours(model: TrayModel, filament_bgr: tuple[int, int, int],
                  rng: np.random.Generator) -> np.ndarray:
    """Shaded, textured colour of every heightfield cell (float32 BGR 0-255)."""
    height = model.height_mm.astype(np.float32)
    gy, gx = np.gradient(height, model.res_mm)
    normal = np.stack([-gx, -gy, np.ones_like(gx)], axis=-1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    shade = AMBIENT + DIFFUSE * np.clip(normal @ LIGHT_DIR.astype(np.float32), 0.0, 1.0)
    texture = (1.0 + 0.05 * _smooth_noise(rng, height.shape, 40) + 0.04 * _smooth_noise(rng, height.shape, 6)
               + 0.025 * rng.standard_normal(height.shape).astype(np.float32))
    colours = np.asarray(filament_bgr, dtype=np.float32)[None, None, :] * (shade * texture)[..., None]
    ys, xs = np.mgrid[0:height.shape[0], 0:height.shape[1]]
    xs_mm, ys_mm = xs * model.res_mm, ys * model.res_mm
    half_pad = (model.pad_mm if model.pad_mm > 0 else model.tag_mm * 1.3) / 2.0
    for corners in model.tag_corners_mm.values():
        cx, cy = corners[:, 0].mean(), corners[:, 1].mean()
        pad = (np.abs(xs_mm - cx) <= half_pad) & (np.abs(ys_mm - cy) <= half_pad)
        colours[pad] = PAPER_BGR * TAG_SHADE
    return np.clip(colours, 0, 255)


def _ray_directions(cam: Intrinsics, pose: Pose, width: int, height: int, scale: float) -> np.ndarray:
    """Unit ray directions in tray frame for a (height, width) grid sampling the full-res image."""
    u = (np.arange(width) + 0.5) / scale - 0.5
    v = (np.arange(height) + 0.5) / scale - 0.5
    uu, vv = np.meshgrid(u, v)
    cam_dirs = np.stack([(uu - cam.cx) / cam.fx, (vv - cam.cy) / cam.fy, np.ones_like(uu)], axis=-1)
    dirs = cam_dirs.reshape(-1, 3) @ pose.rotation  # R^T applied to row vectors
    return dirs / np.linalg.norm(dirs, axis=1, keepdims=True)


def _box_interval(origin: np.ndarray, dirs: np.ndarray, hi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    safe = np.where(np.abs(dirs) < 1e-12, 1e-12, dirs)
    t_a = (0.0 - origin) / safe
    t_b = (hi - origin) / safe
    t_enter = np.maximum(np.minimum(t_a, t_b).max(axis=1), 0.0)
    t_exit = np.maximum(t_a, t_b).min(axis=1)
    return t_enter, t_exit


def _march(height: np.ndarray, res: float, origin: np.ndarray, dirs: np.ndarray,
           t0: np.ndarray, t1: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Marching ray cast; returns (t_hit or NaN, ix, iy) of the first cell the ray is under."""
    ny, nx = height.shape
    t_hit = np.full(len(t0), np.nan)
    hit_ix = np.zeros(len(t0), dtype=np.int64)
    hit_iy = np.zeros(len(t0), dtype=np.int64)
    idx = np.flatnonzero(t1 > t0)
    t = t0.copy()

    def cells(rays: np.ndarray, tt: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        p = origin + tt[:, None] * dirs[rays]
        ix = np.clip(np.rint(p[:, 0] / res), 0, nx - 1).astype(np.int64)
        iy = np.clip(np.rint(p[:, 1] / res), 0, ny - 1).astype(np.int64)
        return p[:, 2], ix, iy

    while idx.size:
        z, ix, iy = cells(idx, t[idx])
        below = z <= height[iy, ix]
        if below.any():
            rays = idx[below]
            lo = np.maximum(t[rays] - MARCH_STEP_MM, t0[rays])
            hi = t[rays].copy()
            for _ in range(BISECT_ITERS):
                mid = 0.5 * (lo + hi)
                zm, mx, my = cells(rays, mid)
                under = zm <= height[my, mx]
                hi = np.where(under, mid, hi)
                lo = np.where(under, lo, mid)
            _, hx, hy = cells(rays, hi)
            t_hit[rays], hit_ix[rays], hit_iy[rays] = hi, hx, hy
        idx = idx[~below]
        t[idx] += MARCH_STEP_MM
        idx = idx[t[idx] <= t1[idx]]
    return t_hit, hit_ix, hit_iy


def _background(origin: np.ndarray, dirs: np.ndarray) -> np.ndarray:
    """Table top (z = 0 plane) or dark void for rays that miss the tray."""
    out = np.tile(FAR_BGR, (len(dirs), 1))
    down = dirs[:, 2] < -1e-6
    t = np.where(down, -origin[2] / np.where(down, dirs[:, 2], -1.0), 0.0)
    pts = origin + t[:, None] * dirs
    grain = 1.0 + 0.05 * np.sin(pts[:, 0] * 0.45 + 2.0 * np.sin(pts[:, 1] * 0.05)) + 0.03 * np.sin(pts[:, 1] * 1.3)
    out[down] = (TABLE_BGR[None, :] * grain[:, None])[down]
    return out


def _water_colour(under: np.ndarray, dirs: np.ndarray, path_mm: np.ndarray, dye_bgr: tuple[int, int, int],
                  dye_alpha: float) -> np.ndarray:
    """Tint terrain colour seen through water and add Fresnel sky reflection and a sun glint."""
    alpha = 1.0 - (1.0 - dye_alpha) ** (1.0 + path_mm / DEPTH_REF_MM)
    tinted = under * (1.0 - alpha[:, None]) + np.asarray(dye_bgr, dtype=np.float64) * alpha[:, None]
    cos_view = np.clip(-dirs[:, 2], 0.0, 1.0)
    fresnel = 0.02 + 0.98 * (1.0 - cos_view) ** 5
    reflect = dirs * np.array([1.0, 1.0, -1.0])
    glint = np.clip(reflect @ LIGHT_DIR, 0.0, 1.0) ** SPEC_POWER * SPEC_GAIN
    return tinted * (1.0 - fresnel[:, None]) + SKY_BGR * fresnel[:, None] + glint[:, None]


def _render_terrain(model: TrayModel, cam: Intrinsics, pose: Pose, level_mm: float | None,
                    cell_colours: np.ndarray, filament_dye: tuple[tuple[int, int, int], float],
                    size: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """Colour (h, w, 3) and per-pixel hit distance (inf if the ray misses the tray)."""
    width, height = size
    iw, ih = max(1, round(width * RENDER_SCALE)), max(1, round(height * RENDER_SCALE))
    origin = camera_position_mm(pose)
    dirs = _ray_directions(cam, pose, iw, ih, RENDER_SCALE)
    hf = model.height_mm
    extent = np.array([(hf.shape[1] - 1) * model.res_mm, (hf.shape[0] - 1) * model.res_mm,
                       float(hf.max()) + TOP_MARGIN_MM])
    t_enter, t_exit = _box_interval(origin, dirs, extent)
    t_hit, hx, hy = _march(hf, model.res_mm, origin, dirs, t_enter, t_exit)
    hit = np.isfinite(t_hit)
    colour = _background(origin, dirs)
    base = cell_colours[hy, hx].astype(np.float64)
    side = hit & (t_hit - t_enter < MARCH_STEP_MM) & (origin[2] + t_enter * dirs[:, 2] < extent[2] - 1e-3)
    base[side] *= SIDE_WALL_DARKEN
    if level_mm is not None:
        dye_bgr, alpha = filament_dye
        safe_dz = np.where(dirs[:, 2] < -1e-9, dirs[:, 2], -1e-9)
        t_water = (level_mm - origin[2]) / safe_dz
        wet = hit & (hf[hy, hx] < level_mm - WET_EPS_MM) & (t_water >= t_enter) & (t_water < t_hit)
        base[wet] = _water_colour(base[wet], dirs[wet], (t_hit - t_water)[wet], dye_bgr, alpha)
    colour[hit] = base[hit]
    dist = np.where(hit, t_hit, np.inf)
    return (colour.reshape(ih, iw, 3).astype(np.float32), dist.reshape(ih, iw).astype(np.float32))


def _draw_tags(model: TrayModel, cam: Intrinsics, pose: Pose, image: np.ndarray, t_hit: np.ndarray,
               z_offset_mm: float = 0.0) -> np.ndarray:
    """Paste real ArUco marker images on the pad tops at full resolution."""
    height, width = image.shape[:2]
    origin = camera_position_mm(pose)
    dirs = _ray_directions(cam, pose, width, height, 1.0)
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, model.tag_dictionary))
    out = image.copy()
    half = model.tag_mm / 2.0
    for tag_id, corners in model.tag_corners_mm.items():
        z = float(corners[0, 2]) + z_offset_mm
        down = dirs[:, 2] < -1e-9
        t_plane = np.where(down, (z - origin[2]) / np.where(down, dirs[:, 2], -1.0), np.inf)
        pts = origin + t_plane[:, None] * dirs
        cx, cy = corners[:, 0].mean(), corners[:, 1].mean()
        inside = down & (np.abs(pts[:, 0] - cx) <= half + TAG_MARGIN_MM) & (np.abs(pts[:, 1] - cy) <= half + TAG_MARGIN_MM)
        inside &= t_plane <= t_hit.reshape(-1) + 0.6
        if not inside.any():
            continue
        marker = cv2.aruco.generateImageMarker(dictionary, tag_id, MARKER_PX)
        map_x = ((pts[:, 0] - (cx - half)) / model.tag_mm * MARKER_PX - 0.5).astype(np.float32).reshape(height, width)
        map_y = (((cy + half) - pts[:, 1]) / model.tag_mm * MARKER_PX - 0.5).astype(np.float32).reshape(height, width)
        sampled = cv2.remap(marker, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=255)
        mask = inside.reshape(height, width)
        paper = (sampled.astype(np.float32) / 255.0)[..., None] * PAPER_BGR * TAG_SHADE
        out[mask] = paper[mask]
    return out


def _add_glare(image: np.ndarray, blobs: int, rng: np.random.Generator) -> np.ndarray:
    out = image.copy()
    h, w = out.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    for _ in range(blobs):
        cx, cy = rng.uniform(0, w), rng.uniform(0, h)
        radius = rng.uniform(*GLARE_RADIUS_RANGE_PX)
        out += (rng.uniform(*GLARE_GAIN_RANGE) * np.exp(-((xs - cx) ** 2 + (ys - cy) ** 2) / (2 * radius ** 2)))[..., None]
    return out


def _jitter_pose(pose: Pose, degrees: float, rng: np.random.Generator) -> Pose:
    if degrees <= 0.0:
        return pose
    delta = cv2.Rodrigues(np.radians(rng.normal(0.0, degrees, 3)))[0]
    rvec = cv2.Rodrigues(delta @ pose.rotation)[0].reshape(3)
    return Pose(rvec, delta @ np.asarray(pose.tvec, dtype=np.float64).reshape(3))


def _degrade(image: np.ndarray, noise: Noise, rng: np.random.Generator) -> np.ndarray:
    out = image.astype(np.float32)
    if noise.glare_blobs > 0:
        out = _add_glare(out, noise.glare_blobs, rng)
    if noise.blur_px > 0:
        out = cv2.GaussianBlur(out, (0, 0), noise.blur_px)
    out = out * noise.brightness
    if noise.gauss_sigma > 0:
        out = out + rng.normal(0.0, noise.gauss_sigma, out.shape).astype(np.float32)
    out = np.clip(out, 0, 255).astype(np.uint8)
    if noise.jpeg_quality > 0:
        ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, int(noise.jpeg_quality)])
        if ok:
            out = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return out


def render(model: TrayModel, cam: Intrinsics, pose: Pose, level_mm: float | None = None, *,
           width: int | None = None, height: int | None = None,
           filament_bgr: tuple[int, int, int] = DEFAULT_FILAMENT_BGR,
           dye_bgr: tuple[int, int, int] = DEFAULT_DYE_BGR, dye_alpha: float = DEFAULT_DYE_ALPHA,
           noise: Noise = Noise(), rng: np.random.Generator | None = None,
           tag_z_offset_mm: float = 0.0, draw_tags: bool = True) -> np.ndarray:
    """Render a BGR frame of the tray with water at ``level_mm`` (None = dry).

    Output size is ``2*cx x 2*cy`` of the intrinsics unless ``width``/``height`` are given.
    """
    rng = rng if rng is not None else np.random.default_rng(0)
    size = (int(width or round(cam.cx * 2)), int(height or round(cam.cy * 2)))
    shot_pose = _jitter_pose(pose, noise.pose_jitter_deg, rng)
    colours = _cell_colours(model, filament_bgr, rng)
    terrain, dist = _render_terrain(model, cam, shot_pose, level_mm, colours, (dye_bgr, dye_alpha), size)
    image = cv2.resize(terrain, size, interpolation=cv2.INTER_LINEAR)
    dist_full = cv2.resize(dist, size, interpolation=cv2.INTER_NEAREST)
    if draw_tags:  # False models a tray whose tag stickers are missing or unreadable
        image = _draw_tags(model, cam, shot_pose, image, dist_full, tag_z_offset_mm)
    return _degrade(image, noise, rng)
