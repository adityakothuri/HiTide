"""Flooded vehicles and people (drone vision plan 7.2-7.5).

Depth at a vehicle comes from the measured water surface, not the car's shape:
depth = wse - ground under the vehicle. The box bottom of a car in water is its WATERLINE, so the
vehicle is located by intersecting that pixel's ray with the water plane z = wse (mapping it onto the
DEM would put the car behind its true spot). The car's shape is never used as a depth gauge: without a
measured water surface a vehicle has no depth and no band.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from vision.camera import Intrinsics, Pose, ray_to_plane
from vision.detect import Det
from vision.grid import GroundGrid

VehicleBand = Literal["none", "wheels", "doors", "windows", "roof"]
PersonSituation = Literal["in_water", "on_vehicle", "dry_near_water", "dry_away", "unknown"]
VEHICLE_CLASSES = frozenset({"car", "truck", "bus", "motorcycle", "boat"})
M_TO_IN = 1 / 0.0254
MAX_VEHICLE_DEPTH_IN = 600.0      # snapshot bound; beyond it the reading is a failure, not a depth


@dataclass(frozen=True)
class Geometry:
    """What's needed to place objects on the ground. None for real photos without a drone pose."""
    cam: Intrinsics
    pose: Pose
    grid: GroundGrid
    wse_m: float | None


@dataclass(frozen=True)
class Vehicle:
    track_id: int
    type: str
    box: tuple[float, float, float, float]
    in_water: bool | None            # None: no informative pixels around it (frame edge, crowd) - not "dry"
    partly_submerged: bool
    xy: tuple[float, float] | None
    depth_at_vehicle_in: float | None
    band: VehicleBand | None
    band_source: Literal["water_surface"] | None


@dataclass(frozen=True)
class Person:
    track_id: int
    box: tuple[float, float, float, float]
    situation: PersonSituation
    xy: tuple[float, float] | None
    on_vehicle_id: int | None


def _clip_box(box, w: int, h: int) -> tuple[int, int, int, int]:
    """Clamp all four bounds into the frame (a negative bound would wrap a numpy slice). Empty -> zero area."""
    if not np.all(np.isfinite(box)):
        return 0, 0, 0, 0
    x1, y1, x2, y2 = box
    cx1, cy1 = min(max(0, int(x1)), w), min(max(0, int(y1)), h)
    cx2, cy2 = min(max(0, int(np.ceil(x2))), w), min(max(0, int(np.ceil(y2))), h)
    return cx1, cy1, max(cx1, cx2), max(cy1, cy2)


def ring_water_fraction(box, water: np.ndarray, expand: float, others: list | None = None,
                        ignore: np.ndarray | None = None) -> float | None:
    """Share of water in the LOWER half of a ring around the box (box grown by `expand`, minus the box).

    Only informative pixels count: pixels inside other detections and `ignore` pixels (blocker labels:
    reflections of cars/trees on the water, other objects) are left out. None if nothing informative is
    left (box at the frame edge, or surrounded by blockers).
    """
    h, w = water.shape
    x1, y1, x2, y2 = box
    dx, dy = expand * (x2 - x1), expand * (y2 - y1)
    ox1, oy1, ox2, oy2 = _clip_box((x1 - dx, y1 - dy, x2 + dx, y2 + dy), w, h)
    ring = np.zeros((h, w), bool)
    mid = min(max(0, int((y1 + y2) / 2)), h)
    ring[max(oy1, mid):oy2, ox1:ox2] = True
    ix1, iy1, ix2, iy2 = _clip_box(box, w, h)
    ring[iy1:iy2, ix1:ix2] = False
    for ob in others or []:
        bx1, by1, bx2, by2 = _clip_box(ob, w, h)
        ring[by1:by2, bx1:bx2] = False
    if ignore is not None:
        ring &= ~ignore | water
    n = int(ring.sum())
    return float(water[ring].mean()) if n else None


def box_lower_water_fraction(box, water: np.ndarray, lower: float = 0.3) -> float:
    h, w = water.shape
    x1, y1, x2, y2 = _clip_box(box, w, h)
    top = int(y2 - lower * (y2 - y1))
    patch = water[top:y2, x1:x2]
    return float(patch.mean()) if patch.size else 0.0


def vehicle_band(depth_in: float, bands: Mapping[str, float]) -> VehicleBand:
    if depth_in <= 0:
        return "none"
    if depth_in >= bands["roof"]:
        return "roof"
    if depth_in >= bands["windows"]:
        return "windows"
    if depth_in >= bands["doors"]:
        return "doors"
    return "wheels"


def _ground_xy(det: Det, geo: Geometry, in_water: bool) -> tuple[float, float] | None:
    u, v = (det.box[0] + det.box[2]) / 2, det.box[3]
    if in_water and geo.wse_m is not None:
        p = ray_to_plane(geo.cam, geo.pose, np.array([[u, v]]), geo.wse_m)[0]
    else:
        from vision.camera import ray_to_terrain

        pts, hit = ray_to_terrain(geo.cam, geo.pose, np.array([[u, v]]), geo.grid.height_at,
                                  t_max=6 * max(geo.pose.z - float(np.nanmin(geo.grid.z)), 1.0))
        p = pts[0] if hit[0] else np.array([np.nan] * 3)
    return None if not np.isfinite(p[:2]).all() else (float(p[0]), float(p[1]))


def _ground_under(xy: tuple[float, float], grid: GroundGrid, radius: float) -> float | None:
    ang = np.linspace(0, 2 * np.pi, 12, endpoint=False)
    rr = np.concatenate([[0.0], np.full(12, radius / 2), np.full(12, radius)])
    aa = np.concatenate([[0.0], ang, ang])
    z = grid.height_at(xy[0] + rr * np.cos(aa), xy[1] + rr * np.sin(aa))
    return None if np.all(np.isnan(z)) else float(np.nanmin(z))


def classify_vehicle(det: Det, water: np.ndarray, others: list, geo: Geometry | None,
                     cfg: Mapping[str, Any], ignore: np.ndarray | None = None) -> Vehicle:
    ocfg, bands = cfg["objects"], cfg["vehicle_band_in"]
    ring = ring_water_fraction(det.box, water, float(ocfg["ring_expand"]), others, ignore)
    in_water = None if ring is None else ring >= float(ocfg["ring_water_frac"])
    partly = bool(in_water) and box_lower_water_fraction(det.box, water) >= float(ocfg["box_water_frac"])
    xy = depth = band = source = None
    if geo is not None:
        xy = _ground_xy(det, geo, bool(in_water))
    if in_water and xy is not None and geo is not None and geo.wse_m is not None:
        ground = _ground_under(xy, geo.grid, float(ocfg["footprint_m"]))
        above = None if ground is None else (geo.wse_m - ground) * M_TO_IN
        # a car "in water" on ground above the water surface is contradictory evidence: no depth, not 0
        if above is not None and 0.0 < above <= MAX_VEHICLE_DEPTH_IN:
            depth = above
            band, source = vehicle_band(depth, bands), "water_surface"
    return Vehicle(det.track_id, det.cls, det.box, in_water, partly, xy, depth, band, source)


def _on_vehicle(person: Det, vehicles: list[Vehicle]) -> int | None:
    """Standing or SEATED on a vehicle that is in water or whose water state is unknown (never a dry one). Reuses the repo rule tuned on the sample photos
    (assess._on_roof: feet in the top 45% of the box, or hips at the roof line); the spec's 'top third'
    misses a seated person whose legs hang over the windshield (flood_01-03)."""
    from vision.assess import _on_roof

    for v in vehicles:
        if v.in_water is not False and _on_roof(list(person.box), list(v.box)):
            return v.track_id
    return None


def classify_person(det: Det, water: np.ndarray, vehicles: list[Vehicle], others: list,
                    water_xy: np.ndarray | None, geo: Geometry | None, cfg: Mapping[str, Any],
                    ignore: np.ndarray | None = None) -> Person:
    """on_vehicle > in_water > dry_near_water (within 30 m of water) > dry_away; unknown if no informative
    pixels surround the person (frame edge, crowd) - never called dry without evidence.

    Without geometry (a photo), 'near water' falls back to: water anywhere in the frame.
    """
    ocfg = cfg["objects"]
    on = _on_vehicle(det, vehicles)
    xy = _ground_xy(det, geo, in_water=False) if geo is not None else None
    if on is not None:
        return Person(det.track_id, det.box, "on_vehicle", xy, on)
    ring = ring_water_fraction(det.box, water, float(ocfg["ring_expand"]), others, ignore)
    if ring is not None and ring >= float(ocfg["ring_water_frac"]):
        if geo is not None and geo.wse_m is not None:
            xy = _ground_xy(det, geo, in_water=True)
        return Person(det.track_id, det.box, "in_water", xy, None)
    if ring is None:
        return Person(det.track_id, det.box, "unknown", xy, None)
    near = bool(water.any())
    if xy is not None and water_xy is not None and len(water_xy):
        near = float(np.min(np.hypot(water_xy[:, 0] - xy[0], water_xy[:, 1] - xy[1]))) <= float(
            ocfg["people_near_water_m"])
    return Person(det.track_id, det.box, "dry_near_water" if near else "dry_away", xy, None)
