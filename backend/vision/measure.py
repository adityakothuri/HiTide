"""Geometric water-level measurement at one critical point from a hover's frames (plan Part A).

frames -> per-frame ground-grid labels -> vote -> edges -> robust WSE (+ level-set cross-check)
       -> road coverage -> depth at road -> band -> confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

import numpy as np

from vision.camera import Intrinsics, Pose, centre
from vision.edges import EdgeSet, RoadGeom, extract_edges
from vision.grid import CellObs, GroundGrid, Seg, label_cells, vote
from vision.water_level import (
    WSE, Confidence, Depth, RoadBand, RoadState, WLParams, depth_at_road, estimate_wse, levelset_wse,
    road_band, road_state, score_confidence,
)

INFERRED_REASON = "water level above road low point (road hidden)"
COARSE_REASON = "zero-shot water mask (coarse edge)"
DRY_CONTRADICTION = "edge/road disagree"
DRY_UNCONFIRMED = "dry road not confirmed"


def _confirm_dry(est: WSE | None, road_min_z: float, low_light: bool, coarse: bool) -> tuple[bool | None, str]:
    """A road is reported dry only if nothing argues otherwise (overview 3: never call a road safe)."""
    if est is not None and est.lo_m > road_min_z:
        return None, DRY_CONTRADICTION            # the measured surface is above the road
    if low_light or coarse or (est is not None and est.hi_m >= road_min_z):
        return None, DRY_UNCONFIRMED
    return False, ""


@dataclass(frozen=True)
class PointContext:
    point_id: str
    grid: GroundGrid
    road: RoadGeom
    cam: Intrinsics
    lut: np.ndarray


@dataclass(frozen=True)
class Measurement:
    road: RoadState
    water_on_road: bool | None
    wse: WSE | None
    levelset: tuple[float, float] | None
    depth: Depth | None
    band: RoadBand | None
    confidence: Confidence
    reasons: tuple[str, ...]          # all reasons: scoring reasons + notes
    notes: tuple[str, ...]            # reasons not produced by scoring (inferred wet, coarse mask)
    contradiction: bool
    low_light: bool
    edges: EdgeSet
    voted: CellObs


def measure(
    ctx: PointContext, frames: list[tuple[Seg, Pose]], params: WLParams, cfg: Mapping[str, Any],
) -> Measurement:
    if not frames:
        raise ValueError("measure needs at least one frame")
    window = int(cfg["segmentation"]["vote_window"])
    recent = frames[-window:]
    obs = [label_cells(ctx.grid, s, ctx.cam, p, ctx.lut, int(cfg["grid"]["occlusion_steps"])) for s, p in recent]
    voted = vote(obs)
    seg, pose = recent[-1]
    ecfg = cfg["edges"]
    edges = extract_edges(voted, ctx.grid, ctx.road, window=int(ecfg["ground_window"]),
                          ground_frac=float(ecfg["ground_frac"]), seg=seg, cam=ctx.cam, pose=pose,
                          samples=int(ecfg["refine_samples"]))
    low, _, _ = ctx.road.low_point_and_axis(ctx.grid)
    low_xyz = np.array([low[0], low[1], ctx.grid.height_at(low[:1], low[1:])[0]])
    slant = float(np.linalg.norm(centre(pose) - low_xyz))
    # ground footprint of one pixel at the road low point: slant/fx across the ray, stretched by
    # 1/sin(grazing angle) along the ground on an oblique view
    grazing = np.arcsin(np.clip((pose.z - low_xyz[2]) / max(slant, 1e-6), 0.2, 1.0))
    gsd = slant / ctx.cam.fx / float(np.sin(grazing))
    coarse = seg.zero_shot_frac >= float(cfg["segmentation"]["zero_shot"]["coarse_frac"])
    if coarse:  # the zero-shot mask is ~352 px across: its boundary is less certain
        params = replace(params, mask_bias_px=2 * params.mask_bias_px)
    est = estimate_wse(edges, params, slant, gsd, float(grazing))
    ls = levelset_wse(voted, ctx.grid)
    rs = road_state(voted, ctx.grid, ctx.road, cfg["road"])
    wet, extra = rs.water_on_road, []
    if wet is None and est is not None and est.lo_m > rs.road_min_z:
        wet, extra = True, [INFERRED_REASON]
    contradiction = False
    if wet is False:
        wet, why = _confirm_dry(est, rs.road_min_z, seg.low_light, coarse)
        if why:
            extra.append(why)
            contradiction = why == DRY_CONTRADICTION
    depth = None
    if est is not None and wet is not False:
        depth = depth_at_road(est, rs.road_min_z, params.dem_error_m, params.range_k)
        contradiction = contradiction or (depth is None and wet is True)
    band = road_band(depth.depth_in, cfg["road_band_in"]) if depth is not None and wet else None
    conf, reasons = score_confidence(est, params, levelset=ls, low_light=seg.low_light,
                                     contradiction=contradiction)
    if wet is not True and conf == "high":   # confidence describes the level; a dry/unknown claim is never "high"
        conf = "medium"
    if coarse:
        extra.append(COARSE_REASON)
    return Measurement(rs, wet, est, ls, depth, band, conf, reasons + tuple(extra), tuple(extra), contradiction,
                       seg.low_light, edges, voted)
