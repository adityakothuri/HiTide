"""Offline Kerrville town: road graph, segment geometry/elevation, distance to the Guadalupe River."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import networkx as nx
import numpy as np
import osmnx as ox
from pyproj import Transformer
from shapely.geometry import LineString, shape
from shapely.ops import transform

from app.config import DATA_DIR

TOWN_DIR = DATA_DIR / "town"
_TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32614", always_xy=True).transform


@dataclass(frozen=True)
class Town:
    graph: nx.MultiDiGraph
    segments_fc: dict[str, Any]
    river_feature: dict[str, Any]
    edge_ids: tuple[str, ...]
    edge_index: dict[str, int]
    elev_m: np.ndarray
    river_dist_m: np.ndarray
    midpoints: np.ndarray  # (n, 2) lon, lat
    bounds: tuple[float, float, float, float]

    def segment_name(self, edge_id: str) -> str:
        props = self.segments_fc["features"][self.edge_index[edge_id]]["properties"]
        return props.get("name") or "unnamed road"


def _fill_nan(elev: np.ndarray) -> np.ndarray:
    if np.isnan(elev).any():
        return np.where(np.isnan(elev), np.nanmedian(elev), elev)
    return elev


@lru_cache(maxsize=1)
def load_town() -> Town:
    segments = json.loads((TOWN_DIR / "segments.geojson").read_text())
    river = json.loads((TOWN_DIR / "river.geojson").read_text())
    graph = ox.load_graphml(TOWN_DIR / "graph.graphml")

    river_utm = transform(_TO_UTM, shape(river["geometry"]))
    feats = segments["features"]
    edge_ids = tuple(f["properties"]["edge_id"] for f in feats)
    elev = _fill_nan(np.array([f["properties"]["elev_m"] for f in feats], dtype=float))

    mids, dists = [], []
    for f in feats:
        line: LineString = shape(f["geometry"])
        mid = line.interpolate(0.5, normalized=True)
        mids.append((mid.x, mid.y))
        dists.append(transform(_TO_UTM, line).distance(river_utm))

    mid_arr = np.array(mids)
    bounds = (float(mid_arr[:, 0].min()), float(mid_arr[:, 1].min()), float(mid_arr[:, 0].max()), float(mid_arr[:, 1].max()))
    return Town(
        graph=graph,
        segments_fc=segments,
        river_feature=river,
        edge_ids=edge_ids,
        edge_index={eid: i for i, eid in enumerate(edge_ids)},
        elev_m=elev,
        river_dist_m=np.array(dists),
        midpoints=mid_arr,
        bounds=bounds,
    )
