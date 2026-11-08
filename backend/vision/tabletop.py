"""Measure the water level on the 3D-printed Kerrville tray with the drone vision pipeline, against CAD truth.

Frames: the pipeline runs in the "ex" frame = the physical print divided uniformly by mm_per_m. A uniform
scale keeps camera geometry exact (pose from ArUco on the table, ray casting, ground sample distance), and
horizontal ex metres equal world metres, so road widths and areas in vision.yaml still mean what they say.
Heights in ex carry the vertical exaggeration; PrintScale.world_from_ex removes it for the report.

Ground truth: the water in a tray is level, so a measured level (caliper on the channel floor) or a poured
volume (volume_curve.json) gives the true rise exactly; the true depth over a road is level - road surface.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

from app.config import DATA_DIR
from sim.print_scale import PrintScale, bathtub_wet, level_for_volume
from vision.camera import Intrinsics, Pose, project, ray_to_terrain
from vision.geom import dist_to_polyline
from vision.config import vision_config
from vision.edges import RoadGeom
from vision.fiducials import detect_tags, solve_pose
from vision.grid import GroundGrid, Seg
from vision.measure import Measurement, PointContext, measure
from vision.segment import clean_water, color_fallback, lut_from_names
from vision.synth import ADE, Noise, apply_noise
from vision.water_level import M_TO_IN, WLParams

MODEL_DIR = DATA_DIR / "print_model"
SKY = ADE["sky"]
BUILDING = ADE["building"]
BLOCKER_MIN_MM = 1.0           # cells this far above the bare tray are building blocks (roads are 0.4 mm)


@dataclass(frozen=True)
class Station:
    id: str
    kind: str
    name: str
    xy: np.ndarray                 # ex metres
    road: np.ndarray | None        # (k, 2) ex metres


@dataclass(frozen=True)
class TabletopModel:
    grid: GroundGrid               # the whole tray in ex metres (terrain + roads + buildings + rim)
    scale: PrintScale
    zref_m: float                  # world low-flow surface (rise 0)
    stations: Mapping[str, Station]
    tags: Mapping[int, np.ndarray]  # tag id -> (4, 3) corners in ex metres
    tag_dict: str
    road_half_width_m: float       # ex = world metres
    curve: tuple[tuple[float, float], ...]   # (level mm, mL)
    size_mm: float
    river: np.ndarray              # channel cells (seed of the bathtub fill), same shape as grid.z
    blocker: np.ndarray            # building cells: water against a wall says nothing about the level

    def mm_to_ex(self, mm):
        return self.scale.ex_m(mm)


@dataclass(frozen=True)
class Reading:
    station: str
    rise_m: float | None
    rise_lo_m: float | None
    rise_hi_m: float | None
    level_mm: float | None
    depth_in: float | None
    depth_lo_in: float | None
    depth_hi_in: float | None
    water_on_road: bool | None
    confidence: str
    edge_points: int = 0
    sides: int = 0
    frames_used: int = 0
    reasons: tuple[str, ...] = ()


def load_model(directory: Path = MODEL_DIR) -> TabletopModel:
    truth_path, manifest_path = directory / "truth.npz", directory / "manifest.json"
    if not truth_path.exists() or not manifest_path.exists():
        raise FileNotFoundError(f"print model not built in {directory}")
    t = np.load(truth_path)
    man = json.loads(manifest_path.read_text())
    scale = PrintScale(float(t["mm_per_m"]), float(t["exaggeration"]), float(t["z_datum_m"]), float(t["base_mm"]))
    res_mm = float(t["res_mm"])
    grid = GroundGrid(0.0, 0.0, float(scale.ex_m(res_mm)), scale.ex_m(t["height_mm"].astype(float)))
    stations = {
        s["id"]: Station(s["id"], s["kind"], s.get("name", ""), scale.ex_m(np.array(s["model_mm"])),
                         None if s["road_mm"] is None else scale.ex_m(np.array(s["road_mm"])))
        for s in man["stations"]
    }
    tags = {int(i): scale.ex_m(c) for i, c in zip(t["fiducial_ids"], t["fiducial_corners_mm"])}
    curve = tuple((r["level_mm"], r["ml"]) for r in json.loads((directory / "volume_curve.json").read_text()))
    return TabletopModel(grid, scale, float(t["zref_m"]), stations, tags, man["fiducials"]["dictionary"],
                         float(scale.ex_m(man["road_half_width_mm"])), curve, float(man["size_mm"][0]),
                         t["river"].astype(bool),
                         _blockers(t["height_mm"], t["terrain_mm"]))


def _blockers(height_mm: np.ndarray, terrain_mm: np.ndarray) -> np.ndarray:
    """Building blocks (well above the bare tray) and the tray rim/pads (all at the rim top)."""
    rim = terrain_mm >= float(terrain_mm.max()) - 1e-3
    return ((height_mm - terrain_mm) > BLOCKER_MIN_MM) | rim


def tabletop_settings(cfg: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    return (cfg or vision_config())["tabletop"]


def wl_params(model: TabletopModel, cfg: Mapping[str, Any] | None = None) -> WLParams:
    """vision.yaml water_level, with the table-scale error budget converted to ex metres."""
    full = cfg or vision_config()
    tcfg = tabletop_settings(full)
    e = model.scale.exaggeration
    base = WLParams.from_config(full["water_level"])
    return replace(
        base,
        dem_error_m=float(model.mm_to_ex(tcfg["print_error_mm"])),
        pose_sigma_m=float(model.mm_to_ex(tcfg["pose_sigma_mm"])),
        pose_sigma_z_m=float(model.mm_to_ex(tcfg["pose_sigma_z_mm"])),
        pose_sigma_deg=float(tcfg["pose_sigma_deg"]),
        mask_bias_px=float(tcfg["mask_bias_px"]),
        tight_in=base.tight_in * e,          # confidence bands are judged on world inches
        wide_in=base.wide_in * e,
    )


def window(model: TabletopModel, station: Station, half_m: float) -> GroundGrid:
    g = model.grid
    ny, nx = g.shape
    j0 = max(0, int((station.xy[0] - half_m - g.x0) / g.res))
    j1 = min(nx, int((station.xy[0] + half_m - g.x0) / g.res) + 1)
    i0 = max(0, int((station.xy[1] - half_m - g.y0) / g.res))
    i1 = min(ny, int((station.xy[1] + half_m - g.y0) / g.res) + 1)
    return GroundGrid(g.x0 + j0 * g.res, g.y0 + i0 * g.res, g.res, g.z[i0:i1, j0:j1])


def station_context(model: TabletopModel, station_id: str, cam: Intrinsics,
                    cfg: Mapping[str, Any] | None = None) -> PointContext:
    st = model.stations[station_id]
    if st.road is None:
        raise ValueError(f"station {station_id} has no printed road to measure against")
    grid = window(model, st, float(tabletop_settings(cfg)["window_half_m"]))
    return PointContext(station_id, grid, RoadGeom(st.road, model.road_half_width_m), cam, lut_from_names())


def wet_cells(model: TabletopModel, level_mm: float) -> np.ndarray:
    """Ground-truth wet mask on the whole tray: level water connected to the river channel."""
    return bathtub_wet(model.grid.z, float(model.mm_to_ex(level_mm)), model.river)


def true_reading(model: TabletopModel, station_id: str, level_mm: float, cam: Intrinsics | None = None) -> Reading:
    """Rise from the level; road depth = level minus the road surface, only where the water reaches the road."""
    ctx = station_context(model, station_id, cam or default_camera())
    g, wet = model.grid, wet_cells(model, level_mm)
    pts = ctx.road.samples(g.res / 2)
    j = np.clip(np.round((pts[:, 0] - g.x0) / g.res).astype(int), 0, g.shape[1] - 1)
    i = np.clip(np.round((pts[:, 1] - g.y0) / g.res).astype(int), 0, g.shape[0] - 1)
    in_window = ~np.isnan(ctx.grid.height_at(pts[:, 0], pts[:, 1]))
    road_mm = g.height_at(pts[:, 0], pts[:, 1]) * model.scale.mm_per_m
    reached = in_window & wet[i, j]
    depth_mm = float(np.max(level_mm - road_mm[reached])) if reached.any() else 0.0
    depth_in = max(0.0, depth_mm) / model.scale.vertical_mm_per_m * M_TO_IN
    rise = model.scale.rise_m(level_mm, model.zref_m)
    return Reading(station_id, rise, rise, rise, level_mm, depth_in, depth_in, depth_in, depth_in > 0, "truth")


def level_from_pour(model: TabletopModel, poured_ml: float) -> float:
    return level_for_volume(list(model.curve), poured_ml)


def to_reading(model: TabletopModel, station_id: str, m: Measurement, frames_used: int) -> Reading:
    s, e = model.scale, model.scale.exaggeration
    if m.wse is None:
        return Reading(station_id, None, None, None, None, None, None, None, m.water_on_road, m.confidence,
                       frames_used=frames_used, reasons=m.reasons)

    def rise(z_ex: float) -> float:
        return float(s.world_from_ex(z_ex) - model.zref_m)

    d = m.depth
    return Reading(
        station_id, rise(m.wse.wse_m), rise(m.wse.lo_m), rise(m.wse.hi_m), m.wse.wse_m * s.mm_per_m,
        None if d is None else d.depth_in / e, None if d is None else d.lo_in / e,
        None if d is None else d.hi_in / e, m.water_on_road, m.confidence, m.wse.n_inliers, m.wse.sides,
        frames_used, m.reasons,
    )


def measure_frames(model: TabletopModel, station_id: str, frames: Sequence[tuple[Seg, Pose]], cam: Intrinsics,
                   cfg: Mapping[str, Any] | None = None) -> Reading:
    full = cfg or vision_config()
    if not frames:
        return Reading(station_id, None, None, None, None, None, None, None, None, "low",
                       reasons=("no frame with a fiducial pose",))
    ctx = station_context(model, station_id, cam, full)
    m = measure(ctx, list(frames), wl_params(model, full), full)
    return to_reading(model, station_id, m, len(frames))


# --- real frames -----------------------------------------------------------------------------------------

def default_camera(width: int = 960, height: int = 720, hfov_deg: float | None = None) -> Intrinsics:
    """Nominal camera. The Tello spec (82.6 deg) is a DIAGONAL FOV; convert it to horizontal for the aspect."""
    if hfov_deg is None:
        dfov = np.radians(float(tabletop_settings()["dfov_deg"]))
        hfov_deg = float(np.degrees(2 * np.arctan(np.tan(dfov / 2) * width / np.hypot(width, height))))
    return Intrinsics.from_hfov(width, height, hfov_deg)


def seg_from_frame(frame_bgr: np.ndarray, cfg: Mapping[str, Any] | None = None) -> Seg:
    """Dyed water by colour: the print is plastic, so ADE20K classes mean nothing here. Dry = earth."""
    full = cfg or vision_config()
    water = clean_water(color_fallback(frame_bgr), float(full["segmentation"]["min_blob_frac"]))
    labels = np.where(water, ADE["water"], ADE["earth"]).astype(np.int16)
    p = cv2.GaussianBlur(water.astype(np.float32), (0, 0), 0.8)
    return Seg(labels, np.clip(p, 0, 1))


def paint_blockers(model: TabletopModel, seg: Seg, cam: Intrinsics, pose: Pose) -> Seg:
    """Label the pixels of known (CAD) building blocks as 'building' so edges never sit on their walls."""
    i, j = np.nonzero(model.blocker)
    g = model.grid
    xyz = np.column_stack([g.x0 + j * g.res, g.y0 + i * g.res, g.z[i, j]])
    uv, depth = project(cam, pose, xyz)
    h, w = seg.labels.shape
    ok = (depth > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)
    mask = np.zeros((h, w), np.uint8)
    mask[uv[ok, 1].astype(int), uv[ok, 0].astype(int)] = 1
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8)).astype(bool)
    labels = np.where(mask & (seg.p_water < 0.5), BUILDING, seg.labels).astype(np.int16)
    return Seg(labels, seg.p_water, seg.low_light, seg.zero_shot_frac)


def frames_with_pose(model: TabletopModel, frames_bgr: Sequence[np.ndarray], cam: Intrinsics,
                     mirror: bool = False) -> list[tuple[Seg, Pose]]:
    if mirror:   # flipping the image mirrors the principal point too
        cam = Intrinsics(cam.fx, cam.fy, cam.width - cam.cx, cam.cy, cam.width, cam.height)
    out = []
    for f in frames_bgr:
        img = cv2.flip(f, 1) if mirror else f
        pose = solve_pose(detect_tags(img, model.tag_dict), model.tags, cam)
        if pose is not None:
            out.append((paint_blockers(model, seg_from_frame(img), cam, pose), pose))
    return out


# --- synthetic frames rendered from the CAD truth (pre-print validation) ---------------------------------

def hover_pose(model: TabletopModel, cfg: Mapping[str, Any] | None = None) -> Pose:
    """Camera over the tray, set back to the south and tilted, high enough to keep all four tags in view."""
    tcfg = tabletop_settings(cfg)
    c = model.size_mm / 2
    x, y, z = (float(model.mm_to_ex(v)) for v in (c, c - tcfg["hover_back_mm"], tcfg["hover_height_mm"]))
    return Pose(x, y, z, 0.0, float(tcfg["hover_pitch_deg"]))


def render_tray(model: TabletopModel, level_mm: float, road: np.ndarray, cam: Intrinsics, pose: Pose,
                roi: GroundGrid) -> tuple[np.ndarray, np.ndarray]:
    """Clean labels (and the label under any water) for the image region covering `roi`.

    Rays march over the WHOLE tray (a window-only grid lets rays slip under terrain just outside it), and a
    hit is wet only where the bathtub fill from the river reaches: real tray water leaves sealed hollows dry.
    """
    g = model.grid
    labels = np.full((cam.height, cam.width), SKY, np.int16)
    under = labels.copy()
    box = _image_box(cam, pose, roi)
    if box is None:
        return labels, under
    u0, v0, u1, v1 = box
    vv, uu = np.mgrid[v0:v1, u0:u1]
    uv = np.column_stack([uu.ravel() + 0.5, vv.ravel() + 0.5])
    t_max = 2.0 * (pose.z - float(np.nanmin(g.z)) + 1.0)
    pts, hit = ray_to_terrain(cam, pose, uv, g.height_at, t_max, steps=256)
    level_ex = float(model.mm_to_ex(level_mm))
    wet_mask = wet_cells(model, level_mm)
    lab = np.full(len(uv), SKY, np.int16)
    und = lab.copy()
    h = pts[hit]
    on_road = dist_to_polyline(h[:, :2], road) <= model.road_half_width_m
    base = np.where(on_road, ADE["road"], ADE["grass"]).astype(np.int16)
    j = np.clip(np.round((h[:, 0] - g.x0) / g.res).astype(int), 0, g.shape[1] - 1)
    i = np.clip(np.round((h[:, 1] - g.y0) / g.res).astype(int), 0, g.shape[0] - 1)
    wet = (h[:, 2] < level_ex) & wet_mask[i, j]
    base = np.where(model.blocker[i, j], BUILDING, base).astype(np.int16)
    lab[hit] = np.where(wet, ADE["water"], base)
    und[hit] = base
    labels[v0:v1, u0:u1] = lab.reshape(v1 - v0, u1 - u0)
    under[v0:v1, u0:u1] = und.reshape(v1 - v0, u1 - u0)
    return labels, under


def _image_box(cam: Intrinsics, pose: Pose, g: GroundGrid) -> tuple[int, int, int, int] | None:
    ny, nx = g.shape
    xs, ys = g.x0 + np.array([0, nx - 1]) * g.res, g.y0 + np.array([0, ny - 1]) * g.res
    zs = [float(np.nanmin(g.z)), float(np.nanmax(g.z))]
    uv, depth = project(cam, pose, np.array([[x, y, z] for x in xs for y in ys for z in zs]))
    if np.any(depth <= 0):
        return None
    u0, v0 = (max(0, int(np.floor(uv[:, k].min())) - 2) for k in (0, 1))
    u1, v1 = min(cam.width, int(np.ceil(uv[:, 0].max())) + 2), min(cam.height, int(np.ceil(uv[:, 1].max())) + 2)
    return None if u1 <= u0 or v1 <= v0 else (u0, v0, u1, v1)


def synthetic_frames(model: TabletopModel, station_id: str, level_mm: float, cam: Intrinsics, n: int = 5,
                     seed: int = 0, cfg: Mapping[str, Any] | None = None) -> list[tuple[Seg, Pose]]:
    """Render a hover over the tray at a water level; the pose handed on is solved from the projected tags."""
    tcfg = tabletop_settings(cfg)
    rng = np.random.default_rng(seed)
    ctx = station_context(model, station_id, cam, cfg)
    base = hover_pose(model, cfg)
    jitter_m, jitter_deg = float(model.mm_to_ex(tcfg["hover_jitter_mm"])), float(tcfg["hover_jitter_deg"])
    px_sigma = float(tcfg["tag_corner_px_sigma"])
    noise = Noise(boundary_px=int(tcfg["synth_boundary_px"]))
    out = []
    for _ in range(n):
        true = base.perturbed(rng, jitter_m, jitter_deg, jitter_m)
        seen = {}
        for tid, c in model.tags.items():
            uv, depth = project(cam, true, c)
            if np.all(depth > 0) and np.all((uv >= 0) & (uv < [cam.width, cam.height])):   # tag fully in frame
                seen[tid] = uv + rng.normal(0, px_sigma, (4, 2))
        est = solve_pose(seen, model.tags, cam)
        if est is None:
            continue
        labels, under = render_tray(model, level_mm, ctx.road.centreline, cam, true, ctx.grid)
        out.append((apply_noise(labels, under, noise, rng), est))
    return out


def synthetic_reading(model: TabletopModel, station_id: str, level_mm: float, seed: int = 0,
                      cam: Intrinsics | None = None) -> Reading:
    cam = cam or default_camera()
    return measure_frames(model, station_id, synthetic_frames(model, station_id, level_mm, cam, seed=seed), cam)
