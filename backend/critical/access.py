"""Which floodable points a node depends on to get out (overview.md 8.1, 8.2), plus truck access once cut off.

A point c is UNAVOIDABLE for node n iff every n -> safe path uses c, i.e. removing c disconnects n.
The k penalized exit routes give a cheap superset (points on every route); the cut test makes it exact.
This is the colleague's single-crossing sensitivity (evidence/analysis.py `reachable(blocked=...)`),
applied per node so it feeds the `dependency` term of the priority score.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

import networkx as nx

SINK = "__safe__"
ROUTE_COUNT = 3
REUSE_PENALTY = 3.0


@dataclass(frozen=True)
class Road:
    edge_id: str
    u: str
    v: str
    length_m: float
    truck_only: bool = False


@dataclass(frozen=True)
class NodeAccess:
    status: Literal["connected", "cut_off"]
    unavoidable: frozenset[str]
    optional: frozenset[str]
    routes: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class TruckRoute:
    edge_ids: tuple[str, ...]
    points: frozenset[str]
    length_m: float


def build_graph(roads: Iterable[Road]) -> nx.MultiGraph:
    """Undirected: in an evacuation people drive either way; keys are edge ids."""
    g = nx.MultiGraph()
    for r in roads:
        g.add_edge(str(r.u), str(r.v), key=r.edge_id, length=float(r.length_m), truck_only=r.truck_only)
    return g


def _view(g: nx.MultiGraph, point_of: dict[str, str], removed: frozenset[str], cars: bool) -> nx.MultiGraph:
    hidden = [(u, v, k) for u, v, k, d in g.edges(keys=True, data=True)
              if point_of.get(k) in removed or (cars and d["truck_only"])]
    return nx.restricted_view(g, [], hidden)


def _with_sink(view: nx.MultiGraph, targets: set[str]) -> nx.MultiGraph:
    h = nx.MultiGraph(view)
    for t in targets:
        if t in h:
            h.add_edge(t, SINK, key=f"sink-{t}", length=0.0, truck_only=False)
    return h


def _path_edges(h: nx.MultiGraph, nodes: list[str], weight: dict) -> tuple[str, ...]:
    edges = []
    for a, b in zip(nodes, nodes[1:]):
        key = min(h[a][b], key=lambda k: weight.get(k, h[a][b][k]["length"]))
        if not key.startswith("sink-"):
            edges.append(key)
    return tuple(edges)


def _routes(h: nx.MultiGraph, origin: str) -> tuple[tuple[str, ...], ...]:
    lengths: dict[str, float] = {k: float(d["length"]) for _, _, k, d in h.edges(keys=True, data=True)}
    weight: dict[str, float] = {}

    def w(_a: str, _b: str, d: dict) -> float:
        return min(weight.get(k, lengths[k]) for k in d)

    found: list[tuple[str, ...]] = []
    for _ in range(ROUTE_COUNT):
        nodes = nx.shortest_path(h, origin, SINK, weight=w)
        route = _path_edges(h, nodes, weight)
        if route not in found:
            found.append(route)
        for k in route:  # penalize reuse so the next route is genuinely different
            weight[k] = weight.get(k, lengths[k]) * REUSE_PENALTY
    return tuple(found)


def _connected(h: nx.MultiGraph, origin: str, point_of: dict[str, str], blocked: str) -> bool:
    hidden = [(u, v, k) for u, v, k in h.edges(keys=True) if point_of.get(k) == blocked]
    return nx.has_path(nx.restricted_view(h, [], hidden), origin, SINK)


def node_access(g: nx.MultiGraph, origin: str, safe: set[str], point_of: dict[str, str],
                removed: frozenset[str] = frozenset()) -> NodeAccess:
    h = _with_sink(_view(g, point_of, removed, cars=True), safe)
    if origin not in h or not nx.has_path(h, origin, SINK):
        return NodeAccess("cut_off", frozenset(), frozenset(), ())
    routes = _routes(h, origin)
    on_route = [{point_of[e] for e in r if e in point_of} for r in routes]
    candidates = set.intersection(*on_route) if on_route else set()
    unavoidable = frozenset(c for c in candidates if not _connected(h, origin, point_of, c))
    optional = frozenset(set().union(*on_route) - unavoidable)
    return NodeAccess("connected", unavoidable, optional, routes)


def truck_access(g: nx.MultiGraph, origin: str, stations: set[str], point_of: dict[str, str],
                 impassable: frozenset[str]) -> TruckRoute | None:
    """Can a high-clearance truck (< 24 in of water) reach a cut-off node? None means boat required."""
    h = _with_sink(_view(g, point_of, impassable, cars=False), stations)
    if origin not in h or not nx.has_path(h, origin, SINK):
        return None
    nodes = nx.shortest_path(h, origin, SINK, weight="length")
    edges = _path_edges(h, nodes, {})
    length = sum(min(d["length"] for d in h[a][b].values()) for a, b in zip(nodes, nodes[1:]))
    return TruckRoute(edges, frozenset(point_of[e] for e in edges if e in point_of), round(length, 1))
