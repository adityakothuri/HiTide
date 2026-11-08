"""Water surface, depth at the road and confidence (drone vision plan section 6; overview 6.3, 9.4, 9.7).

Honesty rules (overview section 3, STATE_OF_THE_UNION "no fake depth"):
- a number is reported only with a range; too little evidence -> None, never a guess;
- water_on_road is tri-state: False only when most of the road is visible and dry, else None;
- there is no "open"/"safe" band.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal, Mapping

import numpy as np

from vision.edges import EdgeSet, RoadGeom
from vision.geom import dist_to_polyline
from vision.grid import GROUND, WATER, CellObs, GroundGrid

M_TO_IN = 1 / 0.0254
MAD_TO_SIGMA = 1.4826
MIN_INLIER_FRAC = 0.6          # below this share of edge points surviving the MAD test, cap confidence
Confidence = Literal["low", "medium", "high"]
RoadBand = Literal["shallow", "caution", "dangerous", "vehicles_float", "boat_only"]


@dataclass(frozen=True)
class WLParams:
    min_inliers: int = 30
    min_side_pts: int = 10
    mad_k: float = 3.0
    mad_floor_m: float = 0.01
    one_side_widen: float = 1.5
    dem_error_m: float = 0.10
    pose_sigma_m: float = 1.0
    pose_sigma_deg: float = 0.5
    pose_sigma_z_m: float = 0.5
    mask_bias_px: float = 2.0
    range_k: float = 1.96
    steep_slope: float = 0.30
    tight_in: float = 3.0
    wide_in: float = 8.0

    @staticmethod
    def from_config(cfg: Mapping[str, Any], **overrides: float) -> "WLParams":
        fields = {k: cfg[k] for k in WLParams.__dataclass_fields__ if k in cfg}
        return replace(WLParams(**fields), **overrides)


@dataclass(frozen=True)
class WSE:
    wse_m: float
    sigma_m: float
    lo_m: float
    hi_m: float
    n_edge: int
    n_inliers: int
    sides: int
    median_slope: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RoadState:
    water_on_road: bool | None
    covered_pct: float | None
    visible_frac: float
    road_min_z: float
    n_road_cells: int


@dataclass(frozen=True)
class Depth:
    depth_in: float
    lo_in: float
    hi_in: float


def slant_sigma_m(params: WLParams, slant_m: float, grazing_rad: float = np.pi / 2) -> float:
    """Horizontal 1-sigma of a mapped ground point from pose error.

    GPS error moves it 1:1. An attitude error delta moves the ray's ground hit by slant*tan(delta)/sin(grazing)
    (stretched along the ground on an oblique view). An altitude error dz slides it by dz/tan(grazing).
    """
    s = max(float(np.sin(grazing_rad)), 0.2)
    att = slant_m * np.tan(np.radians(params.pose_sigma_deg)) / s
    alt = params.pose_sigma_z_m * float(np.cos(grazing_rad)) / s
    return float(np.sqrt(params.pose_sigma_m**2 + att**2 + alt**2))


def _mad_inliers(z: np.ndarray, params: WLParams) -> np.ndarray:
    med = float(np.median(z))
    mad = max(float(np.median(np.abs(z - med))), params.mad_floor_m)
    return np.abs(z - med) <= params.mad_k * MAD_TO_SIGMA * mad


def estimate_wse(edges: EdgeSet, params: WLParams, slant_m: float = 0.0, gsd_m: float = 0.0,
                 grazing_rad: float = np.pi / 2) -> WSE | None:
    """Robust level water surface from edge heights: median, MAD inliers, combined sigma. None if too few.

    sigma combines: edge scatter, DEM error, pose error x bank slope (partly cancels across two banks),
    and segmentation boundary bias x ground sample distance x slope (does NOT cancel: an eroded mask
    reads low on both banks, and the level-set cross-check can't see it either).

    Banks are fitted separately (edges.side = which bank, by the water->ground facing): a sideways pose
    offset shifts the two banks in opposite directions, so a single pooled MAD would keep one bank and
    throw the other away. With two banks the surface is the mean of the per-bank medians and half their
    gap is added to sigma.
    """
    if len(edges) < params.min_inliers:
        return None
    z, side = edges.z, edges.side
    groups = [m for m in (side > 0, side < 0) if m.sum() >= params.min_side_pts]
    if len(groups) == 2:
        inl = np.zeros(len(z), dtype=bool)
        for m in groups:
            idx = np.nonzero(m)[0]
            inl[idx[_mad_inliers(z[idx], params)]] = True
    else:
        inl = _mad_inliers(z, params)
    if inl.sum() < params.min_inliers:
        return None
    sides = sum(int((inl & m).sum() >= params.min_side_pts) for m in (side > 0, side < 0))
    if sides == 2:
        meds = [float(np.median(z[inl & m])) for m in (side > 0, side < 0)]
        wse, gap_sigma = float(np.mean(meds)), abs(meds[0] - meds[1]) / 2
    else:
        wse, gap_sigma = float(np.median(z[inl])), 0.0
    zi = z[inl]
    spread = MAD_TO_SIGMA * max(float(np.median(np.abs(zi - np.median(zi)))), params.mad_floor_m)
    if sides == 2:  # scatter around each bank's own level, not the pooled one
        spread = MAD_TO_SIGMA * max(float(np.median(np.concatenate(
            [np.abs(z[inl & m] - np.median(z[inl & m])) for m in (side > 0, side < 0)]))), params.mad_floor_m)
    med_slope = float(np.median(edges.slope[inl]))
    # a horizontal mapping error moves the edge up/down the bank by error x slope; with two opposing
    # banks the shift partly cancels in the mean, so count half of it there (plus the observed gap)
    map_sigma = slant_sigma_m(params, slant_m, grazing_rad) * med_slope * (0.5 if sides == 2 else 1.0)
    mask_sigma = params.mask_bias_px * gsd_m * med_slope
    sigma = float(np.sqrt(spread**2 + params.dem_error_m**2 + map_sigma**2 + mask_sigma**2 + gap_sigma**2))
    reasons = ["two sides" if sides == 2 else "one side only"]
    if sides < 2:
        sigma *= params.one_side_widen
    if med_slope > params.steep_slope:
        reasons.append("steep bank")
    half = params.range_k * sigma
    return WSE(wse, sigma, wse - half, wse + half, len(edges), int(inl.sum()), sides, med_slope, tuple(reasons))


def levelset_wse(obs: CellObs, grid: GroundGrid) -> tuple[float, float] | None:
    """Independent estimate: the level that best splits seen cells into water (below) and ground (above).

    Uses every labelled cell, not just edges, so a biased boundary or a few bad edges move it less.
    Returns (wse, half width of the near-optimal interval) or None if there's no water or no ground.
    """
    keep = (obs.group == WATER) | (obs.group == GROUND)
    z, wet = grid.z[keep], obs.group[keep] == WATER
    if wet.sum() == 0 or (~wet).sum() == 0:
        return None
    order = np.argsort(z)
    zs, ws = z[order], wet[order]
    # threshold between zs[k-1] and zs[k]: cells below are called water, above ground
    dry_below = np.concatenate([[0], np.cumsum(~ws)])
    wet_above = np.concatenate([[0], np.cumsum(ws[::-1])])[::-1]
    cost = dry_below + wet_above
    best = cost.min()
    ks = np.nonzero(cost <= best + max(1, 0.002 * len(zs)))[0]
    bounds = np.concatenate([[zs[0]], (zs[:-1] + zs[1:]) / 2, [zs[-1]]])
    lo, hi = bounds[ks.min()], bounds[ks.max()]
    return float((lo + hi) / 2), float((hi - lo) / 2)


def road_state(obs: CellObs, grid: GroundGrid, road: RoadGeom, cfg: Mapping[str, Any]) -> RoadState:
    """Share of visible road cells under water, and the tri-state water_on_road."""
    x, y = grid.xy()
    on_road = (dist_to_polyline(np.column_stack([x.ravel(), y.ravel()]), road.centreline)
               <= road.half_width_m).reshape(grid.shape)
    n_road = int(on_road.sum())
    g = obs.group[on_road]
    # only WATER and GROUND cells are evidence; OTHER (unknown class, or water below 0.5) isn't "seen dry"
    seen = (g == WATER) | (g == GROUND)
    n_seen = int(seen.sum())
    _, _, road_min = road.low_point_and_axis(grid)
    visible_frac = n_seen / n_road if n_road else 0.0
    if n_seen == 0:
        return RoadState(None, None, visible_frac, road_min, n_road)
    n_wet = int((g == WATER).sum())
    covered = n_wet / n_seen
    wet_area = n_wet * grid.res**2
    # water collects at the low point: "dry" needs the LOWEST road cells seen, not just most of the road
    z_road = grid.z[on_road]
    low = z_road <= np.nanquantile(z_road, float(cfg.get("low_quantile", 0.10)))
    low_seen = float(seen[low].mean()) if low.any() else 0.0
    # decide on wet AREA, not share: a 10 m dip on a 120 m stretch is still water on the road
    if wet_area >= cfg["wet_min_area_m2"]:
        wet: bool | None = True
    elif (visible_frac >= cfg["dry_visible_frac"] and wet_area < cfg["dry_max_area_m2"]
          and low_seen >= float(cfg.get("dry_low_seen_frac", 0.8))):
        wet = False
    else:
        wet = None
    pct = round(100 * covered, 1) if wet is True or visible_frac >= cfg["dry_visible_frac"] else None
    return RoadState(wet, pct, visible_frac, road_min, n_road)


def depth_at_road(est: WSE, road_min_z: float, road_sigma_m: float = 0.0, range_k: float = 1.96) -> Depth | None:
    """Depth over the lowest point of the road. The range adds the road's own DEM error in quadrature to the
    water-surface range. None if the surface is clearly below the road."""
    half = range_k * float(np.hypot(est.sigma_m, road_sigma_m)) if road_sigma_m > 0 else est.hi_m - est.wse_m
    lo, hi = est.wse_m - half, est.wse_m + half
    if hi < road_min_z:
        return None
    d = (est.wse_m - road_min_z) * M_TO_IN
    return Depth(max(0.0, d), max(0.0, (lo - road_min_z) * M_TO_IN), (hi - road_min_z) * M_TO_IN)


def road_band(depth_in: float, bands: Mapping[str, float]) -> RoadBand:
    """NWS bands from weights.yaml road_status_in. Every band still means water on the road."""
    if depth_in >= bands["boat"]:
        return "boat_only"
    if depth_in >= bands["float"]:
        return "vehicles_float"
    if depth_in >= bands["closed"]:
        return "dangerous"
    if depth_in >= bands["caution"]:
        return "caution"
    return "shallow"


def score_confidence(
    est: WSE | None, params: WLParams, *, levelset: tuple[float, float] | None = None,
    low_light: bool = False, contradiction: bool = False,
) -> tuple[Confidence, tuple[str, ...]]:
    """Plan 6.5 table. high = tight + two sides + estimators agree; low on any hard failure."""
    if est is None:
        reasons = ["too few edge points"] + (["low light"] if low_light else [])
        return "low", tuple(reasons)
    reasons = list(est.reasons)
    caps: list[str] = []
    if est.n_edge and est.n_inliers / est.n_edge < MIN_INLIER_FRAC:
        caps.append("many outlier edges")
    if levelset is None:
        caps.append("no cross-check")
    half_in = (est.hi_m - est.wse_m) * M_TO_IN
    level: Confidence = "medium"
    if half_in <= params.tight_in and est.sides == 2:
        level = "high"
        reasons.append("tight range")
    if half_in > params.wide_in:
        level = "low"
        reasons.append("wide range")
    if "steep bank" in est.reasons and level == "high":
        level = "medium"
    if levelset is not None:
        ls_wse, ls_half = levelset
        if abs(ls_wse - est.wse_m) > max(est.hi_m - est.wse_m, ls_half):
            level = "low"
            reasons.append("estimators disagree")
        else:
            reasons.append("estimators agree")
    if contradiction:
        level = "low"
        reasons.append("edge/road disagree")
    if low_light:
        caps.append("low light")
    if caps:
        level = "medium" if level == "high" else level
        reasons.extend(caps)
    return level, tuple(reasons)

