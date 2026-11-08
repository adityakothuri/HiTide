"""One processed step -> VisionSnapshot. No I/O: callers supply frames, detections, cases and a clock.

Two entry points:
- snapshot_from_hover: posed frames over a known DEM (drone with pose, or synthetic) -> full Part A + B.
- snapshot_from_photo: a frame with no pose/DEM -> water mask + detections only; depth is always null.

Depth comes ONLY from the water edge + elevation map (water_edge_dem). Cars are never used as rulers.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

from vision.alerts import match_case, rules
from vision.camera import Pose
from vision.detect import Det, Persistence
from vision.geom import dist_to_polyline
from vision.grid import BLOCKER, WATER, Seg
from vision.measure import PointContext, measure
from vision.objects import (
    VEHICLE_CLASSES,
    Geometry,
    Person,
    Vehicle,
    classify_person,
    classify_vehicle,
)
from vision.rise import RiseTracker
from vision.segment import lut_from_names
from vision.snapshot import AlertOut, PersonOut, VehicleOut, VisionSnapshot
from vision.water_level import WLParams

M_PER_DEG_LAT = 110_574.0
PHOTO_WET_FRAC = 0.20          # a photo is "water on road" only with this much water or a car in water
BLOCKER_LUT = lut_from_names()
MAX_DEPTH_IN = 600.0           # snapshot bound (50 ft); beyond it the estimate is a failure, not a reading


@dataclass(frozen=True)
class GeoOrigin:
    """Local metres <-> lon/lat around a critical point (equirectangular, fine over a few km)."""
    lon0: float
    lat0: float

    def to_lonlat(self, x: float, y: float) -> tuple[float, float]:
        m_lon = 111_320.0 * math.cos(math.radians(self.lat0))
        return self.lon0 + x / m_lon, self.lat0 + y / M_PER_DEG_LAT


@dataclass(frozen=True)
class StepInput:
    t: float                                   # epoch seconds
    drone_id: str | None = None
    image_url: str | None = None
    source: str = "synthetic"
    simulated: bool = True
    cases: tuple[Mapping[str, Any], ...] = ()
    extra_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PointState:
    frames: tuple[tuple[Seg, Pose], ...] = ()
    rise: RiseTracker = field(default_factory=RiseTracker)
    persistence: Persistence = field(default_factory=Persistence)
    visit: int = 0                             # bumps when the reported pose moves (a new GPS/attitude bias)
    anchor: Pose | None = None                 # pose at the start of the current visit


def _iso(t: float) -> datetime:
    return datetime.fromtimestamp(t, tz=UTC)


def _objects(dets: list[Det], seg: Seg, geo: Geometry | None, water_xy: np.ndarray | None,
             cfg: Mapping[str, Any]) -> tuple[list[Vehicle], list[Person]]:
    water = seg.p_water >= 0.5
    ignore = BLOCKER_LUT[np.clip(seg.labels, 0, len(BLOCKER_LUT) - 1)] == BLOCKER
    boxes = [d.box for d in dets]
    vdets = [d for d in dets if d.cls in VEHICLE_CLASSES]
    vehicles = [classify_vehicle(d, water, [b for b in boxes if b != d.box], geo, cfg, ignore) for d in vdets]
    people = [classify_person(d, water, vehicles, [b for b in boxes if b != d.box], water_xy, geo, cfg, ignore)
              for d in dets if d.cls == "person"]
    return vehicles, people


def _vehicle_out(v: Vehicle, origin: GeoOrigin | None, cases: Iterable, radius: float) -> VehicleOut:
    lon = lat = None
    if v.xy is not None and origin is not None:
        lon, lat = origin.to_lonlat(*v.xy)
    case = match_case(lat, lon, cases, radius) if v.in_water else None
    depth = None if v.depth_at_vehicle_in is None else round(v.depth_at_vehicle_in, 1)
    return VehicleOut(track_id=v.track_id, type=v.type, lat=lat, lon=lon, in_water=v.in_water,
                      partly_submerged=v.partly_submerged, depth_at_vehicle_in=depth, band=v.band,
                      band_source=v.band_source, matched_case_id=case)


def _person_out(p: Person, origin: GeoOrigin | None) -> PersonOut:
    lon = lat = None
    if p.xy is not None and origin is not None:
        lon, lat = origin.to_lonlat(*p.xy)
    return PersonOut(track_id=p.track_id, lat=lat, lon=lon, situation=p.situation, on_vehicle_id=p.on_vehicle_id)


def _vehicle_promotes_wet(wet: bool | None, vehicles: list[Vehicle], ctx: PointContext,
                          cfg: Mapping[str, Any]) -> tuple[bool | None, str]:
    """Plan 7.7: a vehicle in water on the road confirms the road is flooded. One in water elsewhere at least
    stops the road being called dry."""
    wet_vehicles = [v for v in vehicles if v.in_water]
    if not wet_vehicles or wet is True:
        return wet, ""
    reach = ctx.road.half_width_m + float(cfg["objects"]["on_road_margin_m"])
    for v in wet_vehicles:
        if v.xy is not None and dist_to_polyline(np.array([v.xy]), ctx.road.centreline)[0] <= reach:
            return True, "vehicle in water on the road"
    return (None, "vehicle in water nearby") if wet is False else (wet, "")


def _visit(state: PointState, pose: Pose, rcfg: Mapping[str, Any]) -> tuple[int, Pose]:
    """Same visit while the reported pose stays near where it started; else a new visit (new bias)."""
    a = state.anchor
    if a is None:
        return state.visit, pose
    moved = math.hypot(pose.x - a.x, pose.y - a.y) > float(rcfg.get("visit_split_m", 1.0)) or \
        abs(pose.z - a.z) > float(rcfg.get("visit_split_z_m", 0.5))
    return (state.visit + 1, pose) if moved else (state.visit, a)


def snapshot_from_hover(
    ctx: PointContext, origin: GeoOrigin, state: PointState, seg: Seg, pose: Pose, dets: list[Det],
    step: StepInput, params: WLParams, cfg: Mapping[str, Any],
    spread_fn: Callable[[float, float, float], list[str]] | None = None,
) -> tuple[VisionSnapshot, PointState]:
    window = int(cfg["segmentation"]["vote_window"])
    frames = (state.frames + ((seg, pose),))[-window:]
    persistence, confirmed = state.persistence.update(dets)
    m = measure(ctx, list(frames), params, cfg)
    wse = m.wse.wse_m if m.wse is not None else None
    geo = Geometry(ctx.cam, pose, ctx.grid, wse)
    x, y = ctx.grid.xy()
    wmask = m.voted.group == WATER
    water_xy = np.column_stack([x[wmask], y[wmask]])
    vehicles, people = _objects(confirmed, seg, geo, water_xy, cfg)
    conf, reasons = m.confidence, m.reasons
    wet, wet_note = _vehicle_promotes_wet(m.water_on_road, vehicles, ctx, cfg)
    if wet_note:
        reasons = reasons + (wet_note,)
    visit, anchor = _visit(state, pose, cfg["rise"])
    rise = state.rise.add(ctx.point_id, step.t, wse, m.wse.sigma_m, visit) if m.wse is not None else state.rise
    trend = rise.trend(ctx.point_id)

    est = rng = band = None
    method = "none"
    if m.depth is not None and m.depth.hi_in <= MAX_DEPTH_IN:
        est, rng, band, method = m.depth.depth_in, (m.depth.lo_in, m.depth.hi_in), m.band, "water_edge_dem"
    elif m.depth is not None:
        reasons = reasons + ("depth beyond measurable range",)
    radius = float(cfg["alerts"]["match_radius_m"])
    v_out = [_vehicle_out(v, origin, step.cases, radius) for v in vehicles]
    p_out = [_person_out(p, origin) for p in people]
    alerts = rules([v.model_dump() for v in v_out], [p.model_dump() for p in p_out], est, cfg["alerts"])
    low, _, _ = ctx.road.low_point_and_axis(ctx.grid)
    lon, lat = origin.to_lonlat(float(low[0]), float(low[1]))
    # spread the LOW end of the range: indirect evidence must not overstate (plan 6.4, fusion indirect_cap)
    spread = spread_fn(lon, lat, m.wse.lo_m) if spread_fn and m.wse is not None and wet else []
    snap = VisionSnapshot(
        point_id=ctx.point_id, time=_iso(step.t), water_on_road=wet, road_covered_pct=m.road.covered_pct,
        road_visible_pct=round(100 * m.road.visible_frac, 1),
        est_depth_in=None if est is None else round(est, 1), depth_method=method, rising=trend.rising,
        people_seen=len(p_out), confidence=conf, image_url=step.image_url, drone_id=step.drone_id,
        lat=lat, lon=lon,
        water_surface_elev_m=None if wse is None else round(wse, 3),
        water_surface_range_m=None if m.wse is None else (round(m.wse.lo_m, 3), round(m.wse.hi_m, 3)),
        depth_at_road_range_in=None if rng is None else (round(rng[0], 1), round(rng[1], 1)),
        depth_band=band, rise_rate_in_per_hr=trend.rate_in_per_hr, trend=trend.trend,
        edge_points_used=0 if m.wse is None else m.wse.n_inliers, edge_sides=0 if m.wse is None else m.wse.sides,
        vehicles=v_out, people=p_out, alerts=[AlertOut(**a.__dict__) for a in alerts],
        spread_segments=list(spread)[:500], confidence_reasons=list(reasons + step.extra_reasons)[:20],
        source=step.source, simulated=step.simulated,
    )
    return snap, PointState(frames, rise, persistence, visit, anchor)


def snapshot_from_photo(point_id: str, seg: Seg, dets: list[Det], step: StepInput,
                        cfg: Mapping[str, Any]) -> VisionSnapshot:
    """No pose, no DEM: water mask and detections only. Depth is null (no water edge + elevation). Never claims dry."""
    vehicles, people = _objects(dets, seg, None, None, cfg)
    water_frac = float((seg.p_water >= 0.5).mean())
    any_wet_vehicle = any(v.in_water for v in vehicles)
    wet = True if any_wet_vehicle or water_frac >= PHOTO_WET_FRAC else None
    reasons = ["no drone pose/elevation: depth not measured", "single frame (no tracking)"]
    if seg.low_light:
        reasons.append("low light")
    if seg.zero_shot_frac >= float(cfg["segmentation"]["zero_shot"]["coarse_frac"]):
        reasons.append("zero-shot water mask (coarse edge)")
    v_out = [_vehicle_out(v, None, (), 0.0) for v in vehicles]
    p_out = [_person_out(p, None) for p in people]
    alerts = rules([v.model_dump() for v in v_out], [p.model_dump() for p in p_out], None, cfg["alerts"])
    return VisionSnapshot(
        point_id=point_id, time=_iso(step.t), water_on_road=wet,
        road_covered_pct=None, est_depth_in=None, depth_method="none", rising=None, people_seen=len(p_out),
        confidence="low", image_url=step.image_url, drone_id=step.drone_id,
        vehicles=v_out, people=p_out, alerts=[AlertOut(**a.__dict__) for a in alerts],
        confidence_reasons=reasons + list(step.extra_reasons), source=step.source if step.source in ("photo", "video", "live") else "photo",
        simulated=step.simulated,
    )
