"""Build the offline Hill Country region cache (Hunt -> Ingram -> Kerrville). Needs network once.

    uv sync --extra data-build && uv run python -m scripts.build_region_cache

Outputs into data/region/<id>/ (config/regions/<id>.yaml):
  graph.graphml        OSM drive network for the bbox
  segments.geojson     one feature per directed edge: edge_id, u, v, length_m, name, highway, bridge, elev_m
  waterways.geojson    rivers + streams (named ones carry a bed profile: chainage_m, z_bed_m every ~30 m)
  dem30.npz            30 m max-pooled DEM (terrain clearance for drone legs) + its grid transform
  places.json          fire stations, safe-destination candidates, camps / RV parks (generic labels), buildings
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import osmnx as ox
import py3dep
import yaml
from pyproj import Geod
from shapely.geometry import LineString, MultiLineString, mapping
from shapely.ops import linemerge, unary_union

from scripts.build_town_cache import _sample, edge_geometry, sample_points, with_mirrors

BACKEND = Path(__file__).resolve().parents[1]
GEOD = Geod(ellps="WGS84")
BED_STEP_M = 30.0
COORD_DECIMALS = 5
PLACE_TAGS = {
    "amenity": ["fire_station", "hospital", "school", "place_of_worship", "community_centre", "townhall"],
    "tourism": ["camp_site", "caravan_site"],
    "leisure": ["summer_camp"],
}


def load_region(region_id: str) -> dict:
    return yaml.safe_load((BACKEND / "config" / "regions" / f"{region_id}.yaml").read_text())


def bbox_tuple(region: dict) -> tuple[float, float, float, float]:
    b = region["bbox"]
    return b["west"], b["south"], b["east"], b["north"]


def round_geom(geom: dict) -> dict:
    def r(c):
        return [round(c[0], COORD_DECIMALS), round(c[1], COORD_DECIMALS)]
    if geom["type"] == "LineString":
        return {"type": "LineString", "coordinates": [r(c) for c in geom["coordinates"]]}
    if geom["type"] == "MultiLineString":
        return {"type": "MultiLineString", "coordinates": [[r(c) for c in part] for part in geom["coordinates"]]}
    return geom


def fetch_graph(out: Path, bbox):
    path = out / "graph.graphml"
    if path.exists():
        print("Loading cached graph.graphml")
        return ox.load_graphml(path)
    print("Fetching OSM drive network for bbox...")
    graph = with_mirrors(lambda: ox.graph_from_bbox(bbox, network_type="drive", simplify=True))
    print(f"  nodes={graph.number_of_nodes()} edges={graph.number_of_edges()}")
    return graph


def fetch_dem(bbox):
    print("Fetching USGS 3DEP DEM (10 m)...")
    dem = py3dep.get_dem(bbox, resolution=10, crs=4326)
    if dem.rio.crs and dem.rio.crs.to_epsg() != 4326:
        dem = dem.rio.reproject("EPSG:4326")
    print(f"  dem shape={dem.shape} min={float(dem.min()):.1f} max={float(dem.max()):.1f}")
    return dem


def save_dem30(out: Path, dem) -> None:
    """Max-pool 3x3 cells: a conservative (highest) terrain surface for drone clearance."""
    z = np.asarray(dem.values, dtype=np.float32)
    h, w = (z.shape[0] // 3) * 3, (z.shape[1] // 3) * 3
    pooled = np.nanmax(z[:h, :w].reshape(h // 3, 3, w // 3, 3), axis=(1, 3))
    xs, ys = np.asarray(dem.x.values), np.asarray(dem.y.values)
    np.savez_compressed(out / "dem30.npz", z=pooled.astype(np.float32),
                        x0=float(xs[0]), dx=float(xs[3] - xs[0]), y0=float(ys[0]), dy=float(ys[3] - ys[0]))
    print(f"  dem30 shape={pooled.shape}")


def build_segments(graph, dem) -> list[dict]:
    feats = []
    for idx, (u, v, k, data) in enumerate(graph.edges(keys=True, data=True)):
        line = edge_geometry(graph, u, v, data)
        pts = sample_points(line)
        elevs = _sample(dem, np.array([p[0] for p in pts]), np.array([p[1] for p in pts]))
        name = data.get("name", "")
        name = " / ".join(name) if isinstance(name, list) else (name or "")
        hw = data.get("highway")
        feats.append({"type": "Feature", "geometry": round_geom(mapping(line)), "properties": {
            "edge_id": f"{u}-{v}-{k}", "u": int(u), "v": int(v), "key": int(k),
            "length_m": round(float(data.get("length", 0.0)), 1), "name": name,
            "highway": hw if isinstance(hw, str) else str(hw),
            "bridge": str(data.get("bridge", "")) not in ("", "no", "nan", "None"),
            "elev_m": round(float(np.nanmin(elevs)), 2)}})
        graph.edges[u, v, k]["elev_m"] = feats[-1]["properties"]["elev_m"]
        if idx % 5000 == 0:
            print(f"  sampled {idx} edges")
    return feats


def _as_lines(geom) -> list[LineString]:
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return list(geom.geoms)
    return []


def bed_profile(line: LineString, dem) -> list[list[float]]:
    """[chainage_m, lon, lat, z_bed_m] every ~30 m. Bed is forced non-increasing downstream (min-so-far)."""
    length_m = GEOD.geometry_length(line)
    n = max(2, int(length_m / BED_STEP_M) + 1)
    pts = [line.interpolate(f, normalized=True).coords[0] for f in np.linspace(0, 1, n)]
    z = _sample(dem, np.array([p[0] for p in pts]), np.array([p[1] for p in pts])).astype(float)
    z = np.where(np.isnan(z), np.nanmedian(z), z)
    if z[0] < z[-1]:  # digitized upstream->downstream? flip so index 0 is the upstream end
        pts, z = pts[::-1], z[::-1]
    z = np.minimum.accumulate(z)
    return [[round(i * length_m / (n - 1), 1), round(p[0], COORD_DECIMALS), round(p[1], COORD_DECIMALS), round(float(zz), 2)]
            for i, (p, zz) in enumerate(zip(pts, z))]


def build_waterways(bbox, region: dict, dem) -> list[dict]:
    print("Fetching waterways...")
    feats = with_mirrors(lambda: ox.features_from_bbox(bbox, tags={"waterway": ["river", "stream"]}))
    feats = feats[feats.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    names = feats["name"].astype(str) if "name" in feats else None
    roles = {w["name"]: w["role"] for w in region["waterways"]}
    out = []
    for wname, role in roles.items():
        chosen = feats[names == wname] if names is not None else feats.iloc[0:0]
        if not len(chosen):
            print(f"  missing waterway: {wname}")
            continue
        merged = linemerge(unary_union(list(chosen.geometry)))
        parts = sorted(_as_lines(merged), key=lambda g: g.length, reverse=True)
        for i, part in enumerate(parts):
            if GEOD.geometry_length(part) < 300:
                continue
            out.append({"type": "Feature", "geometry": round_geom(mapping(part)), "properties": {
                "id": f"{wname.lower().replace(' ', '_')}_{i}", "name": wname, "role": role,
                "waterway": "river" if role in ("main", "fork") else "stream", "bed": bed_profile(part, dem)}})
    unnamed = feats[(names.isin(list(roles)) == False)] if names is not None else feats  # noqa: E712
    for i, geom in enumerate(unnamed.geometry):
        for j, part in enumerate(_as_lines(geom)):
            out.append({"type": "Feature", "geometry": round_geom(mapping(part)), "properties": {
                "id": f"stream_{i}_{j}", "name": "", "role": "minor", "waterway": "stream", "bed": None}})
    print(f"  waterways: {sum(1 for f in out if f['properties']['bed'])} profiled, {len(out)} total")
    return out


def build_places(bbox) -> dict:
    print("Fetching places...")
    gdf = with_mirrors(lambda: ox.features_from_bbox(bbox, tags=PLACE_TAGS))
    places = []
    for (_, osm_id), row in gdf.iterrows():
        c = row.geometry.centroid
        kind = next((row.get(t) for t in ("amenity", "tourism", "leisure") if isinstance(row.get(t), str)), "")
        places.append({"osm_id": int(osm_id), "kind": kind, "name": row.get("name") if isinstance(row.get("name"), str) else "",
                       "lon": round(c.x, COORD_DECIMALS), "lat": round(c.y, COORD_DECIMALS)})
    print("Fetching building footprints...")
    bld = with_mirrors(lambda: ox.features_from_bbox(bbox, tags={"building": True}))
    bld = bld[bld.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    area = bld.to_crs(32614).geometry.area
    cents = bld.geometry.centroid
    kinds = bld["building"].astype(str) if "building" in bld else None
    buildings = [[round(c.x, COORD_DECIMALS), round(c.y, COORD_DECIMALS), round(float(a)), k]
                 for c, a, k in zip(cents, area, kinds if kinds is not None else ["yes"] * len(bld)) if 40 <= a <= 1500]
    print(f"  places={len(places)} buildings={len(buildings)}")
    return {"places": places, "buildings": buildings}


def main(region_id: str = "hill_country") -> int:
    region = load_region(region_id)
    out = BACKEND.parent / "data" / "region" / region_id
    out.mkdir(parents=True, exist_ok=True)
    bbox = bbox_tuple(region)
    graph = fetch_graph(out, bbox)
    dem = fetch_dem(bbox)
    save_dem30(out, dem)
    feats = build_segments(graph, dem)
    (out / "segments.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    ox.save_graphml(graph, out / "graph.graphml")
    (out / "waterways.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": build_waterways(bbox, region, dem)}))
    (out / "places.json").write_text(json.dumps(build_places(bbox)))
    print(f"Wrote {len(feats)} segments to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
