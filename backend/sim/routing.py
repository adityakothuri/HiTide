"""Routing helpers on the cached drive graph. Edge ids are "u-v-key"."""

from __future__ import annotations

from typing import Any, Iterable

import networkx as nx
from shapely.geometry import LineString, mapping, shape
from shapely.ops import linemerge

from sim.drivers import Route, path_edge_ids
from sim.town import Town


def edge_tuple(edge_id: str) -> tuple[int, int, int]:
    u, v, k = edge_id.split("-")
    return int(u), int(v), int(k)


def edge_start(edge_id: str) -> int:
    return edge_tuple(edge_id)[0]


def edge_end(edge_id: str) -> int:
    return edge_tuple(edge_id)[1]


def dry_route(graph: nx.MultiDiGraph, src: int, dst: int, blocked: Iterable[str], label: str) -> Route | None:
    """Shortest path from src to dst that avoids every blocked edge (both directions)."""
    blocked_tuples = set()
    for eid in blocked:
        u, v, k = edge_tuple(eid)
        blocked_tuples.add((u, v, k))
        if graph.has_edge(v, u, k):
            blocked_tuples.add((v, u, k))
    view = nx.restricted_view(graph, [], list(blocked_tuples))
    try:
        nodes = nx.shortest_path(view, src, dst, weight="length")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None
    if len(nodes) < 2:
        return None
    ids, length = path_edge_ids(view, nodes)
    return Route(label=label, dest_node=dst, edge_ids=ids, length_m=round(length, 1))


def route_geojson(town: Town, edge_ids: Iterable[str]) -> dict[str, Any]:
    lines = [shape(town.segments_fc["features"][town.edge_index[e]]["geometry"]) for e in edge_ids if e in town.edge_index]
    if not lines:
        return {"type": "LineString", "coordinates": []}
    merged = linemerge(lines)
    if isinstance(merged, LineString):
        return mapping(merged)
    coords: list[tuple[float, float]] = []
    for line in lines:
        coords.extend(line.coords)
    return mapping(LineString(coords))


def edge_lengths(town: Town) -> dict[str, float]:
    return {f["properties"]["edge_id"]: float(f["properties"]["length_m"]) for f in town.segments_fc["features"]}
