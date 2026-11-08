"""Floodable critical points and population nodes for a region (overview.md sections 7 and 8.1-8.3).

Offline (scripts/build_region_nodes.py -> data/region/<id>/nodes.json):
1. Floodable points: road segments that cross an unnamed stream, are bridges, or sit within 150 m of a
   named waterway and < 3 m above its normal surface (HAND). Both directions of a road = one point.
2. Safe destinations: main-road nodes at least 12 m above the nearest waterway (or far from any).
3. Households: OSM building centroids (synthetic attributes, seeded) snapped to the road graph, plus
   camps and RV parks as named nodes (GENERIC labels on screen).
4. For every snapped road node: k=3 exit routes, unavoidable points (exact cut test), optional points.
5. Homes with the same (unavoidable, optional) signature form one node (overview 7.1).
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
from scipy.spatial import cKDTree

from critical.access import Road, build_graph, node_access
from sim.region import Region, to_xy

HAND_FLOODABLE_M = 3.0
NEAR_WATER_M = 150.0
HAND_SAFE_M = 12.0
MAIN_ROADS = ("motorway", "trunk", "primary", "secondary")
HOME_KINDS = ("yes", "house", "residential", "detached", "mobile_home", "static_caravan", "apartments",
              "semidetached_house", "bungalow", "cabin")
HOME_AREA_M2 = (60, 600)
SEED = 20250704
OLDER_SHARE = 0.30      # Kerr County is one of Texas' oldest counties (~30 % aged 65+, ACS 2019-2023)
MANUFACTURED_SHARE = 0.12
CARS_HOME_AT_NIGHT = 0.85
CAMP_HOUSEHOLDS = 40
RV_HOUSEHOLDS = 30


@dataclass(frozen=True)
class CriticalPointDef:
    id: str
    kind: str              # crossing | bridge | low_spot
    edge_ids: tuple[str, ...]
    name: str
    lon: float
    lat: float
    waterway: str


@dataclass
class PopNode:
    id: str
    name: str
    kind: str              # homes | camp | rv_park
    town: str
    lon: float
    lat: float
    households: int
    older_share: float
    one_story_share: float
    cars_home_share: float
    road_node: str
    unavoidable: list[str] = field(default_factory=list)
    optional: list[str] = field(default_factory=list)


def town_of(lon: float) -> str:
    return "Hunt" if lon < -99.29 else ("Ingram" if lon < -99.19 else "Kerrville")


def segment_hand(region: Region) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Per segment: lowest height above a named waterway, distance to it, and that waterway's name."""
    n = len(region.edge_ids)
    hand, dist, name = np.full(n, np.inf), np.full(n, np.inf), [""] * n
    for ref in region.refs:
        z = region.chains[ref.chain].z_ref_m[ref.sample_idx]
        h = region.elev_m[ref.seg_idx] - z
        for i, hh, dd in zip(ref.seg_idx, h, ref.dist_m):
            if hh < hand[i]:
                hand[i], dist[i], name[i] = hh, dd, ref.chain
    return hand, dist, name


def floodable_points(region: Region, hand: np.ndarray, dist: np.ndarray, ww: list[str]) -> list[CriticalPointDef]:
    feats = region.segments_fc["features"]
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, f in enumerate(feats):
        p = f["properties"]
        eid = p["edge_id"]
        minor = eid in region.minor_crossings
        low = dist[i] <= NEAR_WATER_M and hand[i] < HAND_FLOODABLE_M
        if minor or p.get("bridge") or low:
            groups[(min(p["u"], p["v"]), max(p["u"], p["v"]), p["key"])].append(i)
    points = []
    for n, (key, idxs) in enumerate(sorted(groups.items())):
        i = idxs[0]
        p = feats[i]["properties"]
        eid = p["edge_id"]
        kind = "bridge" if p.get("bridge") or region.minor_crossings.get(eid) else (
            "crossing" if eid in region.minor_crossings or dist[i] < 40 else "low_spot")
        points.append(CriticalPointDef(f"cp-{n:04d}", kind, tuple(feats[j]["properties"]["edge_id"] for j in idxs),
                                       p.get("name") or "Unnamed road", float(region.mid[i, 0]), float(region.mid[i, 1]),
                                       ww[i] or "unnamed creek"))
    return points


def access_graph(region: Region):
    roads = [Road(f["properties"]["edge_id"], str(f["properties"]["u"]), str(f["properties"]["v"]),
                  float(f["properties"]["length_m"])) for f in region.segments_fc["features"]]
    return build_graph(roads)


def safe_nodes(region: Region, hand: np.ndarray, point_edges: set[str]) -> set[str]:
    safe = set()
    for i, f in enumerate(region.segments_fc["features"]):
        p = f["properties"]
        if p["edge_id"] in point_edges or not any(h in p.get("highway", "") for h in MAIN_ROADS):
            continue
        if hand[i] >= HAND_SAFE_M:
            safe.update({str(p["u"]), str(p["v"])})
    return safe


def _snap(region: Region):
    ids = list(region.graph.nodes)
    xy = to_xy(np.array([region.graph.nodes[n]["x"] for n in ids]), np.array([region.graph.nodes[n]["y"] for n in ids]))
    tree = cKDTree(xy)
    def snap(lon: float, lat: float) -> str:
        return str(ids[int(tree.query(to_xy(np.array([lon]), np.array([lat])))[1][0])])
    return snap


def households(region: Region) -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    out = []
    for lon, lat, area, kind in region.buildings:
        if kind not in HOME_KINDS or not HOME_AREA_M2[0] <= area <= HOME_AREA_M2[1]:
            continue
        manufactured = kind in ("mobile_home", "static_caravan") or rng.random() < MANUFACTURED_SHARE
        out.append({"lon": lon, "lat": lat, "older": rng.random() < OLDER_SHARE, "one_story": manufactured,
                    "car_home": rng.random() < CARS_HOME_AT_NIGHT})
    return out


def _special_nodes(region: Region) -> list[dict[str, Any]]:
    counters: Counter = Counter()
    out = []
    for p in region.places:
        if p["kind"] in ("camp_site", "summer_camp"):
            kind, hh, label = "camp", CAMP_HOUSEHOLDS, "Riverside youth camp"
        elif p["kind"] == "caravan_site":
            kind, hh, label = "rv_park", RV_HOUSEHOLDS, "RV park"
        else:
            continue
        town = town_of(p["lon"])
        counters[(label, town)] += 1
        letter = chr(ord("A") + counters[(label, town)] - 1)
        out.append({"kind": kind, "households": hh, "name": f"{label} {letter}, {town}", "lon": p["lon"], "lat": p["lat"]})
    return out


def build_nodes(region: Region) -> dict[str, Any]:
    hand, dist, ww = segment_hand(region)
    points = floodable_points(region, hand, dist, ww)
    point_of = {e: p.id for p in points for e in p.edge_ids}
    g = access_graph(region)
    safe = safe_nodes(region, hand, set(point_of))
    snap = _snap(region)
    homes = households(region)
    by_node: dict[str, list[dict]] = defaultdict(list)
    for h in homes:
        by_node[snap(h["lon"], h["lat"])].append(h)
    specials = _special_nodes(region)
    for s in specials:
        s["road_node"] = snap(s["lon"], s["lat"])
    access: dict[str, Any] = {}
    for rn in set(by_node) | {s["road_node"] for s in specials}:
        a = node_access(g, rn, safe, point_of) if rn not in safe else None
        access[rn] = (sorted(a.unavoidable), sorted(a.optional), a.status) if a else ([], [], "connected")
    nodes: list[PopNode] = []
    groups: dict[tuple, list[tuple[str, dict]]] = defaultdict(list)
    for rn, hs in by_node.items():
        unav, opt, status = access[rn]
        if unav or opt or status == "cut_off":
            for h in hs:
                groups[(tuple(unav), tuple(opt))].append((rn, h))
    for n, ((unav, opt), members) in enumerate(sorted(groups.items(), key=lambda kv: -len(kv[1]))):
        hs = [h for _, h in members]
        lon, lat = float(np.mean([h["lon"] for h in hs])), float(np.mean([h["lat"] for h in hs]))
        road_node = Counter(rn for rn, _ in members).most_common(1)[0][0]
        town = town_of(lon)
        nodes.append(PopNode(f"node-{n:03d}", f"{town} homes ({len(hs)})", "homes", town, round(lon, 5), round(lat, 5),
                             len(hs), round(np.mean([h["older"] for h in hs]), 3), round(np.mean([h["one_story"] for h in hs]), 3),
                             round(np.mean([h["car_home"] for h in hs]), 3), road_node, list(unav), list(opt)))
    for k, s in enumerate(specials):
        unav, opt, _ = access[s["road_node"]]
        nodes.append(PopNode(f"site-{k:02d}", s["name"], s["kind"], town_of(s["lon"]), s["lon"], s["lat"], s["households"],
                             0.0 if s["kind"] == "camp" else OLDER_SHARE, 0.0 if s["kind"] == "camp" else 1.0,
                             0.5, s["road_node"], unav, opt))
    used = {p for nd in nodes for p in nd.unavoidable + nd.optional}
    return {"region": region.id, "points": [asdict(p) for p in points if p.id in used],
            "all_floodable": len(points), "safe_nodes": sorted(safe), "nodes": [asdict(nd) for nd in nodes],
            "households_total": len(homes), "households_exposed": sum(nd.households for nd in nodes if nd.kind == "homes")}
