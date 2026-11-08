"""Alternative routes between two points, each labelled with the flooding on it (the phone's "Choose a route").

Option 1 is the plain fastest way (it may cross water: the person should see that). The others avoid known
flooding: confirmed-flooded roads are removed, likely ones cost x50, unknown x3 (the region router's penalties),
and each found route's roads are penalized so the next option is genuinely different. Wording rule: a route is never
called safe; the best a route can be is "no flooding reported".
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Mapping

import networkx as nx

from critical.flood_layer import GeometryIndex, road_key
from routing.instructions import PENALTY

Coord = tuple[float, float]

MAX_OPTIONS = 3
REUSE_PENALTY = 4.0          # roads already used by an earlier option cost this much more
DRIVE_SPEED_MPS = 11.0       # about 40 km/h in town, for a rough time
SAME_ROUTE_SHARE = 0.85      # an option sharing this much length with an earlier one is not a real alternative
MAX_NAMED = 2
TOP_LABEL = "Least flooding reported"
RANK = {"confirmed_flooded": 3, "likely_flooded": 2, "unknown": 1, "open": 0}


@dataclass(frozen=True)
class RouteOption:
    id: str
    label: str
    via: tuple[str, ...]
    length_m: float
    minutes: int
    lines: tuple[tuple[Coord, ...], ...]
    flooded: tuple[str, ...]
    likely: tuple[str, ...]
    unknown_roads: int
    edge_ids: tuple[str, ...] = field(default=(), repr=False)

    @property
    def status(self) -> str:
        return "flooded" if self.flooded else "likely" if self.likely else "clear"

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "via": list(self.via), "length_m": round(self.length_m, 1),
                "minutes": self.minutes, "status": self.status, "flooded": list(self.flooded),
                "likely": list(self.likely), "unknown_roads": self.unknown_roads,
                "coords": [[list(c) for c in line] for line in self.lines]}


def nearest_node(index: GeometryIndex, lon: float, lat: float) -> str | None:
    """The graph node at the start of the road vertex closest to a point (town scale, flat-earth distance)."""
    best, best_d = None, float("inf")
    for eid, coords in index.coords.items():
        for x, y in coords:
            d = (x - lon) ** 2 + (y - lat) ** 2
            if d < best_d:
                best, best_d = eid, d
    return best.split("-", 1)[0] if best else None


def edge_statuses(segments: Iterable[Mapping[str, Any]], point_of: Mapping[str, str],
                  point_status: Mapping[str, str]) -> dict[str, str]:
    """Worst known status per edge: from its crossing (if any) and from the segment picture."""
    out: dict[str, str] = {e: point_status.get(p, "unknown") for e, p in point_of.items()}
    for s in segments:
        eid, st = str(s.get("edge_id") or ""), str(s.get("status") or "open")
        if eid and RANK.get(st, 0) > RANK.get(out.get(eid, "open"), 0):
            out[eid] = st
    return out


def _path(g: nx.MultiGraph, a: str, b: str, edge_cost: Callable[[str, dict], float | None]) -> list[str] | None:
    def cost(_u: str, _v: str, d: dict) -> float | None:
        costs = [c for k, attrs in d.items() if (c := edge_cost(k, attrs)) is not None]
        return min(costs) if costs else None

    try:
        nodes = nx.shortest_path(g, a, b, weight=cost)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None
    edges = []
    for u, v in zip(nodes, nodes[1:]):
        usable = [(c, k) for k, attrs in g[u][v].items() if (c := edge_cost(k, attrs)) is not None]
        edges.append(min(usable)[1])
    return edges


def _describe(i: int, label: str, edges: list[str], g_len: Mapping[str, float], status: Mapping[str, str],
              index: GeometryIndex) -> RouteOption:
    length = sum(g_len.get(e, 0.0) for e in edges)
    by_name: dict[str, float] = {}
    for e in edges:
        n = index.names.get(e, "")
        if n and n != "Unnamed road":
            by_name[n] = by_name.get(n, 0.0) + g_len.get(e, 0.0)
    via = tuple(n for n, _ in sorted(by_name.items(), key=lambda kv: -kv[1])[:MAX_NAMED])

    def named(st: str) -> tuple[str, ...]:
        return tuple(dict.fromkeys(index.names.get(e, "a road") for e in edges if status.get(e) == st))

    return RouteOption(
        id=f"r{i}", label=label, via=via, length_m=length, minutes=max(1, round(length / DRIVE_SPEED_MPS / 60)),
        lines=tuple(index.coords[e] for e in edges if e in index.coords),
        flooded=named("confirmed_flooded"), likely=named("likely_flooded"),
        unknown_roads=sum(1 for e in edges if status.get(e) == "unknown"), edge_ids=tuple(edges))


def route_options(g: nx.MultiGraph, index: GeometryIndex, status: Mapping[str, str],
                  start: str, end: str) -> list[RouteOption]:
    lengths = {k: float(attrs.get("length", 0.0)) for _u, _v, k, attrs in g.edges(keys=True, data=True)}
    found: list[list[str]] = []
    labels: list[str] = []

    fastest = _path(g, start, end, lambda k, a: float(a.get("length", 0.0)))
    if fastest:
        found.append(fastest)
        labels.append("Fastest")

    used: set[str] = set()
    for label in ("Avoids confirmed flooding", "Another way"):
        def aware(k: str, a: dict, used: set[str] = used) -> float | None:
            st = status.get(k, "open")
            if st == "confirmed_flooded":
                return None
            reused = road_key(k) in used   # both directions of a road are parallel edges: compare roads, not keys
            return float(a.get("length", 0.0)) * PENALTY.get(st, 1.0) * (REUSE_PENALTY if reused else 1.0)

        p = _path(g, start, end, aware)
        if p is None:
            break
        used.update(road_key(e) for e in p)
        if any(_overlap(p, q, lengths) >= SAME_ROUTE_SHARE for q in found):
            continue
        found.append(p)
        labels.append(label)
        if len(found) >= MAX_OPTIONS:
            break
    described = sorted((_describe(i, lab, p, lengths, status, index) for i, (lab, p) in enumerate(zip(labels, found))),
                       key=_least_flooding_first)
    if len(described) > 1 and described[0].label != "Fastest":   # the top option says why it is on top
        described[0] = replace(described[0], label=TOP_LABEL)
    return described


_STATUS_ORDER = {"clear": 0, "likely": 1, "flooded": 2}


def _least_flooding_first(o: RouteOption) -> tuple[int, int, int, int]:
    """Fewest reported problems on top: no flooding reported, then likely, then reported flooding; then time."""
    return (_STATUS_ORDER[o.status], len(o.flooded) + len(o.likely), o.unknown_roads, o.minutes)


def _overlap(a: list[str], b: list[str], lengths: Mapping[str, float]) -> float:
    """Share of a's length on roads b also uses (either direction)."""
    total = sum(lengths.get(e, 0.0) for e in a) or 1.0
    roads_b = {road_key(e) for e in b}
    return sum(lengths.get(e, 0.0) for e in a if road_key(e) in roads_b) / total
