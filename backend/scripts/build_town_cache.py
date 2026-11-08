"""Build the offline Kerrville town cache: OSM drive network, river line, road elevations.

Run once (needs network):  uv run python -m scripts.build_town_cache
Outputs into data/town/:
  graph.graphml        drive network (osmnx)
  segments.geojson     one feature per directed edge: edge_id, u, v, length_m, name, elev_m (min along edge)
  river.geojson        Guadalupe River centerline
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import osmnx as ox
import py3dep
from shapely.geometry import LineString, mapping
from shapely.ops import linemerge, unary_union

CENTER = (30.0474, -99.1403)  # Kerrville, TX (lat, lon)
DIST_M = 4500
SAMPLE_STEP_DEG = 0.0002  # ~20 m
OUT = Path(__file__).resolve().parents[2] / "data" / "town"


OVERPASS_MIRRORS = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.private.coffee/api",
]
# Fallback: hand-traced Guadalupe River centerline through Kerrville (lon, lat), west -> east.
RIVER_FALLBACK = [
    (-99.1850, 30.0420), (-99.1700, 30.0440), (-99.1560, 30.0455), (-99.1450, 30.0462),
    (-99.1380, 30.0448), (-99.1300, 30.0430), (-99.1200, 30.0425), (-99.1100, 30.0440),
    (-99.1000, 30.0455), (-99.0900, 30.0470),
]


def with_mirrors(fn):
    last = None
    for url in OVERPASS_MIRRORS:
        ox.settings.overpass_url = url
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - try next mirror
            print(f"  {url} failed: {exc.__class__.__name__}")
            last = exc
    raise RuntimeError("all Overpass mirrors failed") from last


def fetch_graph():
    path = OUT / "graph.graphml"
    if path.exists():
        print("Loading cached graph.graphml")
        return ox.load_graphml(path)
    print("Fetching OSM drive network...")
    graph = with_mirrors(lambda: ox.graph_from_point(CENTER, dist=DIST_M, network_type="drive", simplify=True))
    ox.save_graphml(graph, path)
    print(f"  nodes={graph.number_of_nodes()} edges={graph.number_of_edges()}")
    return graph


def fetch_river():
    print("Fetching Guadalupe River line...")
    try:
        feats = with_mirrors(lambda: ox.features_from_point(CENTER, tags={"waterway": "river"}, dist=DIST_M + 2000))
    except RuntimeError:
        print("  using hand-traced fallback river line")
        return LineString(RIVER_FALLBACK), "fallback"
    return _merge_river(feats), "osm"


def _merge_river(feats):
    feats = feats[feats.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    named = feats[feats.get("name", "").astype(str).str.contains("Guadalupe", na=False)]
    chosen = named if len(named) else feats
    merged = linemerge(unary_union(list(chosen.geometry)))
    print(f"  river parts={len(chosen)} type={merged.geom_type}")
    return merged


def edge_geometry(graph, u, v, data) -> LineString:
    if "geometry" in data:
        return data["geometry"]
    return LineString([(graph.nodes[u]["x"], graph.nodes[u]["y"]), (graph.nodes[v]["x"], graph.nodes[v]["y"])])


def sample_points(line: LineString) -> list[tuple[float, float]]:
    n = max(2, int(line.length / SAMPLE_STEP_DEG) + 1)
    return [line.interpolate(f, normalized=True).coords[0] for f in np.linspace(0, 1, n)]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    graph = fetch_graph()
    river, river_source = fetch_river()

    west, south, east, north = _bounds(graph)
    print("Fetching USGS 3DEP DEM (10 m)...")
    dem = py3dep.get_dem((west, south, east, north), resolution=10, crs=4326)
    dem = dem.rio.reproject("EPSG:4326") if dem.rio.crs and dem.rio.crs.to_epsg() != 4326 else dem
    print(f"  dem shape={dem.shape} min={float(dem.min()):.1f} max={float(dem.max()):.1f}")

    features = []
    for idx, (u, v, k, data) in enumerate(graph.edges(keys=True, data=True)):
        line = edge_geometry(graph, u, v, data)
        pts = sample_points(line)
        xs = np.array([p[0] for p in pts])
        ys = np.array([p[1] for p in pts])
        elevs = _sample(dem, xs, ys)
        name = data.get("name", "")
        if isinstance(name, list):
            name = " / ".join(name)
        features.append({
            "type": "Feature",
            "geometry": mapping(line),
            "properties": {
                "edge_id": f"{u}-{v}-{k}",
                "u": int(u),
                "v": int(v),
                "key": int(k),
                "length_m": round(float(data.get("length", 0.0)), 1),
                "name": name or "",
                "highway": data["highway"] if isinstance(data.get("highway"), str) else str(data.get("highway")),
                "elev_m": round(float(np.nanmin(elevs)), 2),
            },
        })
        graph.edges[u, v, k]["elev_m"] = features[-1]["properties"]["elev_m"]
        if idx % 1000 == 0:
            print(f"  sampled {idx} edges")

    (OUT / "segments.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    (OUT / "river.geojson").write_text(json.dumps({"type": "Feature", "geometry": mapping(river), "properties": {"name": "Guadalupe River", "source": river_source}}))
    ox.save_graphml(graph, OUT / "graph.graphml")
    print(f"Wrote {len(features)} segments to {OUT}")
    return 0


def _bounds(graph):
    xs = [d["x"] for _, d in graph.nodes(data=True)]
    ys = [d["y"] for _, d in graph.nodes(data=True)]
    pad = 0.002
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def _sample(dem, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    import xarray as xr

    return dem.sel(x=xr.DataArray(xs, dims="p"), y=xr.DataArray(ys, dims="p"), method="nearest").values


if __name__ == "__main__":
    sys.exit(main())
