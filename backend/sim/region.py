"""Offline Hill Country region (Hunt -> Ingram -> Kerrville): roads, waterways with bed profiles, places, DEM.

Built by scripts/build_region_cache.py. Everything the flood model needs per tick is precomputed here:
each road segment's nearest point on every named waterway (within that waterway's lateral reach),
and which segments cross an unnamed stream (low-water crossings).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import osmnx as ox
from scipy.spatial import cKDTree
from shapely import STRtree
from shapely.geometry import shape

from app.config import DATA_DIR, region_settings
from sim.town import _fill_nan, _fix_bridges

M_PER_DEG_LAT = 110_574.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(30.05))


def to_xy(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Local equirectangular metres (accurate to < 0.5 % across a 35 km region)."""
    return np.column_stack([np.asarray(lon) * M_PER_DEG_LON, np.asarray(lat) * M_PER_DEG_LAT])


@dataclass(frozen=True)
class WaterChain:
    name: str
    role: str                 # main | fork | tributary
    s_m: np.ndarray           # chainage, 0 = upstream end
    lon: np.ndarray
    lat: np.ndarray
    z_ref_m: np.ndarray       # low-flow water surface (DEM), non-increasing downstream

    def nearest(self, lon: float, lat: float) -> int:
        d = to_xy(self.lon, self.lat) - to_xy(np.array([lon]), np.array([lat]))
        return int(np.argmin(np.hypot(d[:, 0], d[:, 1])))


@dataclass(frozen=True)
class SegmentRef:
    """Segments within reach of one chain: which segments, their nearest sample, lateral distance."""
    chain: str
    seg_idx: np.ndarray
    sample_idx: np.ndarray
    dist_m: np.ndarray


@dataclass
class Region:
    id: str
    cfg: dict[str, Any]
    graph: nx.MultiDiGraph
    segments_fc: dict[str, Any]
    edge_ids: tuple[str, ...]
    edge_index: dict[str, int]
    elev_m: np.ndarray
    mid: np.ndarray                    # (n, 2) lon/lat of each segment's lowest-ish midpoint
    chains: dict[str, WaterChain]
    refs: tuple[SegmentRef, ...]
    minor_crossings: dict[str, bool]   # edge_id -> is a bridge
    places: list[dict[str, Any]]
    buildings: list[list[Any]]
    dem: dict[str, Any]

    def terrain(self, lon: float, lat: float) -> float:
        """30 m max-pooled DEM (conservative for drone clearance). Outside the grid: region median."""
        d = self.dem
        i, j = int(round((lat - d["y0"]) / d["dy"])), int(round((lon - d["x0"]) / d["dx"]))
        z = d["z"]
        if 0 <= i < z.shape[0] and 0 <= j < z.shape[1] and np.isfinite(z[i, j]):
            return float(z[i, j])
        return d["median"]


def _chains(features: list[dict]) -> dict[str, WaterChain]:
    parts: dict[str, list[dict]] = {}
    for f in features:
        p = f["properties"]
        if p.get("bed"):
            parts.setdefault(p["name"], []).append(p)
    chains = {}
    for name, ps in parts.items():
        seen, ordered = set(), []
        for p in sorted(ps, key=lambda q: -q["bed"][0][3]):  # upstream (highest) first
            ends = (tuple(p["bed"][0][1:3]), tuple(p["bed"][-1][1:3]))
            if ends in seen:  # braid around an island: same start and end, keep one
                continue
            seen.add(ends)
            ordered.append(p["bed"])
        s, lon, lat, z, offset = [], [], [], [], 0.0
        for bed in ordered:
            for row in bed:
                s.append(offset + row[0]); lon.append(row[1]); lat.append(row[2]); z.append(row[3])
            offset = s[-1]
        z_arr = np.minimum.accumulate(np.array(z))
        chains[name] = WaterChain(name, ps[0]["role"], np.array(s), np.array(lon), np.array(lat), z_arr)
    return chains


def _refs(chains: dict[str, WaterChain], mid: np.ndarray, reach: dict[str, float]) -> tuple[SegmentRef, ...]:
    pts = to_xy(mid[:, 0], mid[:, 1])
    refs = []
    for name, ch in chains.items():
        tree = cKDTree(to_xy(ch.lon, ch.lat))
        dist, idx = tree.query(pts)
        keep = dist <= reach[ch.role]
        refs.append(SegmentRef(name, np.nonzero(keep)[0], idx[keep], dist[keep]))
    return tuple(refs)


def _minor_crossings(waterways: list[dict], segs: list[dict]) -> dict[str, bool]:
    lines = [shape(f["geometry"]) for f in waterways if not f["properties"].get("bed")]
    if not lines:
        return {}
    tree = STRtree(lines)
    out = {}
    for f in segs:
        geom = shape(f["geometry"])
        hits = tree.query(geom, predicate="intersects")
        if len(hits):
            out[f["properties"]["edge_id"]] = bool(f["properties"].get("bridge"))
    return out


def _midpoints(segs: list[dict]) -> np.ndarray:
    out = []
    for f in segs:
        c = f["geometry"]["coordinates"]
        out.append(c[len(c) // 2])
    return np.array(out, dtype=float)


@lru_cache(maxsize=2)
def load_region(region_id: str = "hill_country") -> Region:
    cfg = region_settings(region_id)
    root: Path = DATA_DIR / "region" / region_id
    graph = ox.load_graphml(root / "graph.graphml")
    fc = json.loads((root / "segments.geojson").read_text())
    segs = fc["features"]
    edge_ids = tuple(f["properties"]["edge_id"] for f in segs)
    elev = _fill_nan(np.array([f["properties"]["elev_m"] for f in segs], dtype=float))
    elev = _fix_bridges(graph, edge_ids, elev)
    ww = json.loads((root / "waterways.geojson").read_text())["features"]
    chains = _chains(ww)
    mid = _midpoints(segs)
    dem_npz = np.load(root / "dem30.npz")
    z = dem_npz["z"]
    dem = {"z": z, "x0": float(dem_npz["x0"]), "dx": float(dem_npz["dx"]), "y0": float(dem_npz["y0"]),
           "dy": float(dem_npz["dy"]), "median": float(np.nanmedian(z))}
    places = json.loads((root / "places.json").read_text())
    return Region(region_id, cfg, graph, fc, edge_ids, {e: i for i, e in enumerate(edge_ids)}, elev, mid,
                  chains, _refs(chains, mid, cfg["lateral_reach_m"]), _minor_crossings(ww, segs),
                  places["places"], places["buildings"], dem)
