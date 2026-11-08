"""Where to go: a per-user route to higher ground, for the app's map and the voice assistant.

Reuses the region's evacuation router (routing.instructions.route_out): confirmed-flooded crossings are removed,
likely and unknown ones are heavily penalized. Wording rules (overview 10.3): never call a road or route safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import networkx as nx

from routing.instructions import TURN_AROUND, route_out

M_PER_KM = 1000.0
MAX_NAMED_ROADS = 3

STAY = ("You look to be on higher ground. Stay where you are until the water goes down. "
        "Do not drive into water. " + TURN_AROUND)
NO_ROUTE = ("No clear way out by road right now. Do not drive through water. If water is rising around you, "
            "get to the highest ground you can reach on foot and stay out of moving water.")


@dataclass(frozen=True)
class Directions:
    text: str
    road_names: tuple[str, ...] = ()
    length_m: float = 0.0
    coords: tuple[tuple[tuple[float, float], ...], ...] = field(default_factory=tuple)
    avoid: tuple[str, ...] = ()
    kind: str = "route"  # route | stay | none

    def public(self) -> dict[str, Any]:
        return {"text": self.text, "road_names": list(self.road_names), "length_m": self.length_m,
                "coords": [[list(c) for c in line] for line in self.coords], "avoid": list(self.avoid),
                "kind": self.kind}


def origin_node(edge_id: str | None) -> str | None:
    """Edge ids are 'u-v-key'; start from u."""
    if not edge_id or "-" not in edge_id:
        return None
    return edge_id.split("-", 1)[0]


def _avoid_text(avoid: tuple[str, ...]) -> str:
    if not avoid:
        return ""
    return f" Avoid {', '.join(avoid[:MAX_NAMED_ROADS])}: water is reported there."


def _phrase(road_names: tuple[str, ...], current: str | None, km: float) -> str:
    """Never tell someone stopped on a flooded road to go 'by' that road: start from it, then name the way out."""
    rest = road_names[1:] if current and road_names and road_names[0] == current else road_names
    via = ", then ".join(rest[:MAX_NAMED_ROADS]) or "the nearest main road"
    lead = f"Leave {current} and head" if current and rest is not road_names else "Head"
    return f"{lead} for higher ground by {via}, about {km:.1f} km. This way avoids known flooding."


def directions_for(graph: nx.MultiGraph, safe: set[str], point_of: Mapping[str, str], status: Mapping[str, str],
                   names: Mapping[str, str], coords: Mapping[str, tuple[tuple[float, float], ...]],
                   edge_id: str | None, advice: str, avoid: tuple[str, ...] = ()) -> Directions:
    if advice == "stay_on_high_ground":
        return Directions(STAY, avoid=avoid, kind="stay")
    origin = origin_node(edge_id)
    route = route_out(graph, origin, safe, point_of, dict(status), dict(names)) if origin else None
    if route is None:
        return Directions(NO_ROUTE + _avoid_text(avoid), avoid=avoid, kind="none")
    if not route.edge_ids:  # already at a safe node
        return Directions(STAY, avoid=avoid, kind="stay")
    current = names.get(edge_id or "")
    text = f"{_phrase(route.road_names, current, route.length_m / M_PER_KM)}{_avoid_text(avoid)} {TURN_AROUND}"
    lines = tuple(coords[e] for e in route.edge_ids if e in coords)
    return Directions(text, route.road_names, route.length_m, lines, avoid)


def flooded_roads_near(assessment: Mapping[str, Any]) -> tuple[str, ...]:
    """Road names the assessment reports water on: the worst point, then roads ahead and on the planned route."""
    hz = assessment.get("hazard") or {}
    names: list[str] = []
    wp = hz.get("worst_point") or {}
    if wp.get("status") in ("confirmed_flooded", "likely_flooded") and wp.get("name"):
        names.append(wp["name"])
    for hit in list(hz.get("ahead") or []) + list(hz.get("route") or []):
        flooded = hit.get("point_status") in ("confirmed_flooded", "likely_flooded") or (hit.get("depth_in") or 0) > 0
        if flooded and hit.get("road_name"):
            names.append(hit["road_name"])
    return tuple(dict.fromkeys(names))
