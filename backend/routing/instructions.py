"""Route out for a node (overview.md 10.2) and the safety wording rules (10.3).

Edge cost = length x flood penalty: open x1, unknown x3, likely x50; confirmed flooded is removed.
We never say a road is safe: "this route avoids known flooding" + the turn-around rule.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from critical.access import SINK, with_sink

PENALTY = {"open": 1.0, "unknown": 3.0, "likely_flooded": 50.0}
TURN_AROUND = "If you see water on the road, turn around."


@dataclass(frozen=True)
class RouteOut:
    edge_ids: tuple[str, ...]
    road_names: tuple[str, ...]
    length_m: float


def route_out(g: nx.MultiGraph, origin: str, safe: set[str], point_of: dict[str, str],
              point_status: dict[str, str], names: dict[str, str]) -> RouteOut | None:
    def edge_cost(k: str, attrs: dict) -> float | None:
        st = point_status.get(point_of.get(k, ""), "open")
        if st == "confirmed_flooded":
            return None
        return attrs.get("length", 0.0) * PENALTY.get(st, 1.0)

    def cost(_a: str, _b: str, d: dict) -> float | None:
        costs = [c for k, attrs in d.items() if (c := edge_cost(k, attrs)) is not None]
        return min(costs) if costs else None  # None hides the edge from Dijkstra

    h = with_sink(g, safe)  # shared, built once: no 8k-edge copy per call
    try:
        nodes = nx.shortest_path(h, origin, SINK, weight=cost)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None
    edges, length = [], 0.0
    for a, b in zip(nodes, nodes[1:]):
        if b == SINK:
            break
        usable = [(c, k) for k, attrs in h[a][b].items() if (c := edge_cost(k, attrs)) is not None]
        _, k = min(usable)  # same cost as the search, so a flooded parallel edge is never chosen
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
    return (f"HiTide: flash flooding near {node_name}. Leave now for high ground by {via}. "
            f"This route avoids known flooding. {TURN_AROUND} Reply SAFE, HELP, or LEFT.")


def shelter_message(first_name: str) -> str:
    return (f"Hi {first_name}, this is HiTide. Water is over every road out of your area. "
            "Do not drive. Go to the highest floor or high ground now. We have told responders where you are.")
