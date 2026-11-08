"""Route out for a node (overview.md 10.2) and the safety wording rules (10.3).

Edge cost = length x flood penalty: open x1, unknown x3, likely x50; confirmed flooded is removed.
We never say a road is safe: "this route avoids known flooding" + the turn-around rule.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

PENALTY = {"open": 1.0, "unknown": 3.0, "likely_flooded": 50.0}
SINK = "__safe__"
TURN_AROUND = "If you see water on the road, turn around."


@dataclass(frozen=True)
class RouteOut:
    edge_ids: tuple[str, ...]
    road_names: tuple[str, ...]
    length_m: float


def route_out(g: nx.MultiGraph, origin: str, safe: set[str], point_of: dict[str, str],
              point_status: dict[str, str], names: dict[str, str]) -> RouteOut | None:
    def cost(_a: str, _b: str, d: dict) -> float | None:
        best = None
        for k, attrs in d.items():
            st = point_status.get(point_of.get(k, ""), "open")
            if st == "confirmed_flooded":
                continue
            c = attrs.get("length", 0.0) * PENALTY.get(st, 1.0)
            best = c if best is None or c < best else best
        return best  # None hides the edge from Dijkstra

    h = nx.MultiGraph(g)
    for s in safe:
        if s in h:
            h.add_edge(s, SINK, key=f"sink-{s}", length=0.0)
    try:
        nodes = nx.shortest_path(h, origin, SINK, weight=cost)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None
    edges, length = [], 0.0
    for a, b in zip(nodes, nodes[1:]):
        if b == SINK:
            break
        k = min((k for k in h[a][b]), key=lambda k: h[a][b][k].get("length", 0.0))
        edges.append(k)
        length += h[a][b][k].get("length", 0.0)
    ordered_names: list[str] = []
    for e in edges:
        n = names.get(e, "")
        if n and n != "Unnamed road" and (not ordered_names or ordered_names[-1] != n):
            ordered_names.append(n)
    return RouteOut(tuple(edges), tuple(ordered_names), round(length, 1))


def route_message(node_name: str, route: RouteOut) -> str:
    via = ", then ".join(route.road_names[:3]) or "the nearest main road"
    return (f"State Farm Flood Watch: flash flooding near {node_name}. Leave now by {via}. "
            f"This route avoids known flooding. {TURN_AROUND} Reply SAFE, HELP, or LEFT.")


def shelter_message(first_name: str) -> str:
    return (f"Hi {first_name}, this is State Farm Flood Watch. Water is over every road out of your area. "
            "Do not drive. Go to the highest floor or high ground now. We have told responders where you are.")
