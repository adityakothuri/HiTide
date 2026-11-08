"""A compact flood picture for one map window: the phone app's version of the dashboard's flood layers.

The loop snapshot lists non-open road segments without geometry, so geometry comes from the static region.
Directed pairs (u-v and v-u) are merged into one road. Only non-open roads are sent; "open" is the map's base.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

BBox = tuple[float, float, float, float]  # min_lon, min_lat, max_lon, max_lat

MAX_SPAN_DEG = 0.6  # about 60 km: enough for a town or the whole Hill Country window, not the state
STATUS_ORDER = {"confirmed_flooded": 3, "likely_flooded": 2, "unknown": 1, "open": 0}


def parse_bbox(raw: str) -> BBox:
    """'minLon,minLat,maxLon,maxLat' -> tuple. Raises ValueError on anything malformed or too large."""
    parts = raw.split(",")
    if len(parts) != 4:
        raise ValueError("bbox needs 4 numbers")
    min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    values = (min_lon, min_lat, max_lon, max_lat)
    if any(v != v or v in (float("inf"), float("-inf")) for v in values):
        raise ValueError("bbox must be finite")
    if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
        raise ValueError("bbox is out of range or inverted")
    if max_lon - min_lon > MAX_SPAN_DEG or max_lat - min_lat > MAX_SPAN_DEG:
        raise ValueError("bbox is too large")
    return min_lon, min_lat, max_lon, max_lat


def road_key(edge_id: str) -> str:
    """'u-v-k' and 'v-u-k' are the same road in both directions."""
    parts = edge_id.split("-")
    if len(parts) < 3:
        return edge_id
    u, v, k = parts[0], parts[1], "-".join(parts[2:])
    a, b = sorted((u, v))
    return f"{a}-{b}-{k}"


@dataclass(frozen=True)
class GeometryIndex:
    """edge_id -> (name, coords). Built once per region; read-only afterwards."""

    coords: Mapping[str, tuple[tuple[float, float], ...]]
    names: Mapping[str, str]

    @classmethod
    def from_features(cls, features: Iterable[Mapping[str, Any]]) -> "GeometryIndex":
        coords: dict[str, tuple[tuple[float, float], ...]] = {}
        names: dict[str, str] = {}
        for f in features:
            props = f.get("properties") or {}
            eid = props.get("edge_id")
            geom = (f.get("geometry") or {}).get("coordinates")
            if not eid or not geom:
                continue
            coords[eid] = tuple((round(float(x), 5), round(float(y), 5)) for x, y in geom)
            names[eid] = props.get("name") or "Unnamed road"
        return cls(coords, names)


def _inside(lon: float, lat: float, b: BBox) -> bool:
    return b[0] <= lon <= b[2] and b[1] <= lat <= b[3]


def _touches(coords: Iterable[tuple[float, float]], b: BBox) -> bool:
    return any(_inside(x, y, b) for x, y in coords)


def flood_segments(segments: Iterable[Mapping[str, Any]], index: GeometryIndex, b: BBox) -> list[dict[str, Any]]:
    """Non-open roads touching the window, one entry per road, worst status of its two directions."""
    roads: dict[str, dict[str, Any]] = {}
    for s in segments:
        status = str(s.get("status", "open"))
        eid = str(s.get("edge_id") or "")
        geom = index.coords.get(eid)
        if status == "open" or not geom or not _touches(geom, b):
            continue
        key = road_key(eid)
        prev = roads.get(key)
        if prev is None or STATUS_ORDER.get(status, 0) > STATUS_ORDER.get(prev["status"], 0):
            roads[key] = {"id": key, "status": status, "name": index.names.get(eid, "Unnamed road"),
                          "coords": [list(c) for c in geom]}
    return sorted(roads.values(), key=lambda r: (-STATUS_ORDER.get(r["status"], 0), r["id"]))


def flood_points(points: Mapping[str, Mapping[str, Any]], status: Mapping[str, str], b: BBox) -> list[dict[str, Any]]:
    """Every low-water crossing / bridge / low spot in the window with its current status (unknown is never open)."""
    out = []
    for pid, p in points.items():
        lon, lat = float(p["lon"]), float(p["lat"])
        if _inside(lon, lat, b):
            out.append({"id": pid, "name": p.get("name") or "Crossing", "kind": p.get("kind", "crossing"),
                        "status": status.get(pid, "unknown"), "lon": lon, "lat": lat})
    return sorted(out, key=lambda p: (-STATUS_ORDER.get(p["status"], 0), p["id"]))


def flood_gauges(gauges: Iterable[Mapping[str, Any]], b: BBox) -> list[dict[str, Any]]:
    keep = ("site", "name", "lon", "lat", "online", "stage_ft", "observed_at", "flood_category", "rate_ft_per_hr")
    return [{k: g.get(k) for k in keep} for g in gauges
            if g.get("lon") is not None and _inside(float(g["lon"]), float(g["lat"]), b)]


def build_flood_layer(snapshot: Mapping[str, Any], points: Mapping[str, Mapping[str, Any]],
                      status: Mapping[str, str], index: GeometryIndex, b: BBox) -> dict[str, Any]:
    return {
        "at": snapshot.get("sim_time"),
        "mode": snapshot.get("mode"),
        "bbox": list(b),
        "segments": flood_segments(snapshot.get("segments", []), index, b),
        "points": flood_points(points, status, b),
        "gauges": flood_gauges(snapshot.get("gauges", []), b),
        "alerts": [{"id": a.get("id"), "headline": a.get("headline"), "level": a.get("level"),
                    "emergency": bool(a.get("emergency"))} for a in snapshot.get("alerts", [])],
    }


_INDEXES: dict[int, GeometryIndex] = {}


def geometry_index(region: Any) -> GeometryIndex:
    """One index per region object (built on first use, about 8k segments)."""
    key = id(region)
    if key not in _INDEXES:
        _INDEXES[key] = GeometryIndex.from_features(region.segments_fc["features"])
    return _INDEXES[key]


_road_key = road_key  # backwards-compatible alias
