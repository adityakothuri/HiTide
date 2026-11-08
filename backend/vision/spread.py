"""Spread one drone reading to nearby roads (drone vision plan 6.4, corrected).

The spec's "flood every cell below the observed surface within 1 km" assumes level water. The Guadalupe
falls ~1-2 m/km, so instead we take the observed RISE above normal flow at the drone point
(wse - z_ref(s_obs)) and apply it along the same river chain within reach_m of chainage, with the exact
per-segment formula RegionFlood uses (a road can't sit below normal flow + freeboard). Results are
indirect evidence: likely_flooded at most (fusion.yaml indirect_cap), never confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sim.hand_flood import LOW_WATER_FREEBOARD_M
from sim.region import Region

M_TO_IN = 1 / 0.0254


@dataclass(frozen=True)
class SpreadSeg:
    edge_id: str
    est_depth_in: float
    status: str = "likely_flooded"
    source: str = "drone_wse_spread"


@dataclass(frozen=True)
class ChainRef:
    chain: str
    sample_idx: int
    z_ref_m: float
    dist_m: float


def nearest_chain(region: Region, lon: float, lat: float, max_dist_m: float = 300.0) -> ChainRef | None:
    from sim.region import to_xy

    p = to_xy(np.array([lon]), np.array([lat]))[0]
    best: ChainRef | None = None
    for name, ch in region.chains.items():
        d = np.hypot(*(to_xy(ch.lon, ch.lat) - p).T)
        k = int(np.argmin(d))
        if d[k] <= max_dist_m and (best is None or d[k] < best.dist_m):
            best = ChainRef(name, k, float(ch.z_ref_m[k]), float(d[k]))
    return best


def spread(region: Region, lon: float, lat: float, wse_m: float, reach_m: float = 1000.0,
           exclude: frozenset[str] = frozenset()) -> list[SpreadSeg]:
    """Segments on the same chain within reach_m (along the river) that the observed rise floods."""
    ref = nearest_chain(region, lon, lat)
    if ref is None:
        return []
    rise = wse_m - ref.z_ref_m
    if rise <= 0:
        return []
    ch = region.chains[ref.chain]
    s_obs = ch.s_m[ref.sample_idx]
    depth = np.zeros(len(region.edge_ids))
    for sr in region.refs:
        if sr.chain != ref.chain:
            continue
        near = np.abs(ch.s_m[sr.sample_idx] - s_obs) <= reach_m
        seg, z_ref = sr.seg_idx[near], ch.z_ref_m[sr.sample_idx[near]]
        road = np.maximum(region.elev_m[seg], z_ref + LOW_WATER_FREEBOARD_M)
        d = np.nan_to_num(np.maximum(0.0, z_ref + rise - road), nan=0.0) * M_TO_IN
        np.maximum.at(depth, seg, d)
    hits = np.nonzero(depth > 0)[0]
    return [SpreadSeg(region.edge_ids[i], round(float(depth[i]), 1)) for i in hits
            if region.edge_ids[i] not in exclude]
