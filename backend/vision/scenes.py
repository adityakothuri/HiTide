"""Synthetic hover anchored at a real Hill Country critical point, flooded to the July 4 2025 replay truth.

Real: point location, its road segments' elevation (10 m 3DEP minimum), the river's normal-flow surface
z_ref and the gauge-driven rise at time t (RegionFlood truth). Synthetic: the local terrain shape (a
valley with the road dipping to its real low point) and the camera frames. So the pipeline's depth can
be checked against the same truth the scenario uses.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from sim.hand_flood import LOW_WATER_FREEBOARD_M
from sim.region import Region
from sim.region_flood import RegionFlood
from vision.spread import nearest_chain
from vision.synth import Scene, valley_scene

M_TO_IN = 1 / 0.0254


@dataclass(frozen=True)
class AnchoredScene:
    point_id: str
    lon: float
    lat: float
    scene: Scene
    truth_depth_in: float        # RegionFlood truth over the point's road segments at t
    chain: str
    rise_m: float


def point(region_points: dict, point_id: str) -> dict:
    if point_id not in region_points:
        raise KeyError(f"unknown critical point {point_id}")
    return region_points[point_id]


def anchored_scene(region: Region, flood: RegionFlood, p: dict, t: float, bank_slope: float = 0.10) -> AnchoredScene:
    ref = nearest_chain(region, p["lon"], p["lat"], max_dist_m=2000.0)
    if ref is None:
        raise ValueError(f"{p['id']} is not near a modelled river chain")
    rise = float(np.nan_to_num(flood.chain_rise(ref.chain, t, False)[ref.sample_idx], nan=0.0))
    idx = [region.edge_index[e] for e in p["edge_ids"] if e in region.edge_index]
    if not idx or not np.isfinite(region.elev_m[idx]).any():
        raise ValueError(f"{p['id']} has no road segments with an elevation")
    road_z = max(float(np.nanmin(region.elev_m[idx])), ref.z_ref_m + LOW_WATER_FREEBOARD_M)
    truth = float(flood.truth_depth_in(t)[idx].max()) if idx else 0.0
    wse = ref.z_ref_m + rise
    # banks must rise above the flood inside the 60 m window or no water edge is visible at all
    slope = max(bank_slope, (wse - road_z + 1.0) / 45.0)
    base = valley_scene(wse_above_bed_m=0.0, bank_slope=slope, bed_z=road_z)
    scene = replace(base, wse_m=wse)
    return AnchoredScene(p["id"], float(p["lon"]), float(p["lat"]), scene, truth, ref.chain, rise)
