"""Drone vision alert rules (drone vision plan 7.6-7.7). Pure: findings in, prioritised alerts out.

Every alert goes to a human operator first; nothing here contacts 911 (plan 7.7, overview 13).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from drone.dispatch import distance_m

Priority = Literal["critical", "high", "medium", "low"]
PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
CLOSED_CASE_STATES = frozenset({"resolved"})


@dataclass(frozen=True)
class Alert:
    priority: Priority
    kind: str
    message: str
    track_id: int | None
    lat: float | None
    lon: float | None
    depth_in: float | None
    boat_required: bool
    case_id: str | None


def match_case(lat: float | None, lon: float | None, cases: Iterable[Mapping[str, Any]], radius_m: float) -> str | None:
    """Nearest open case within radius_m of an in-water vehicle (Drive Safe & Save stall)."""
    if lat is None or lon is None:
        return None
    best: tuple[float, str] | None = None
    for c in cases:
        if c.get("state") in CLOSED_CASE_STATES or c.get("lat") is None or c.get("lon") is None:
            continue
        d = distance_m(lat, lon, c["lat"], c["lon"])
        if d <= radius_m and (best is None or d < best[0]):
            best = (d, c["id"])
    return None if best is None else best[1]


def _vehicle_depth(v: Mapping[str, Any]) -> float | None:
    """Measured from the water surface only; a car's shape is never a depth gauge."""
    d = v.get("depth_at_vehicle_in")
    return None if d is None else float(d)


def rules(vehicles: list[Mapping[str, Any]], people: list[Mapping[str, Any]], road_depth_in: float | None,
          cfg: Mapping[str, Any]) -> list[Alert]:
    """Plan 7.7 table. vehicles/people are snapshot dicts (matched_case_id already filled)."""
    boat_in, review_in = float(cfg["boat_in"]), float(cfg["review_in"])
    out: list[Alert] = []
    by_id = {v["track_id"]: v for v in vehicles}
    wet_vehicles = {k: v for k, v in by_id.items() if v.get("in_water")}
    for p in people:
        sit, ll = p.get("situation"), (p.get("lat"), p.get("lon"))
        if sit == "in_water":
            boat = road_depth_in is None or road_depth_in > boat_in   # unmeasured: assume no dry approach
            out.append(Alert("critical", "person_in_water", "Person in the water", p["track_id"], *ll,
                             road_depth_in, boat, None))
        elif sit == "on_vehicle":
            v = by_id.get(p.get("on_vehicle_id"), {})
            depth = _vehicle_depth(v) if v else None
            depth = depth if depth is not None else road_depth_in
            # no measured depth: assume no dry approach until an operator says otherwise
            boat = depth is None or depth > boat_in
            out.append(Alert("critical", "person_on_vehicle", "Person on a vehicle in the water", p["track_id"],
                             *ll, depth, boat, v.get("matched_case_id") if v else None))
        elif sit == "unknown":
            out.append(Alert("medium", "person_unclear", "Person near the flood, water state not visible: take a closer look",
                             p["track_id"], *ll, None, False, None))
        elif sit == "dry_near_water":
            out.append(Alert("low", "person_near_water", "Person on dry ground near water", p["track_id"], *ll,
                             None, False, None))
    occupied = {p.get("on_vehicle_id") for p in people if p.get("situation") == "on_vehicle"}
    for v in wet_vehicles.values():
        depth, ll = _vehicle_depth(v), (v.get("lat"), v.get("lon"))
        boat = depth is None or depth > boat_in   # unmeasured: no dry approach assumed
        if v["track_id"] in occupied:
            continue  # already raised as person_on_vehicle (carries the case id)
        if v.get("matched_case_id"):
            out.append(Alert("critical", "vehicle_matches_case", "Vehicle in water matches a stalled insured car",
                             v["track_id"], *ll, depth, boat, v["matched_case_id"]))
        elif depth is None or depth > review_in:
            out.append(Alert("high", "vehicle_review", "Vehicle in water: occupied or abandoned? Request a closer look",
                             v["track_id"], *ll, depth, boat, None))
        else:
            out.append(Alert("medium", "vehicle_logged", "Vehicle in shallow water",
                             v["track_id"], *ll, depth, False, None))
    for v in by_id.values():
        if v.get("in_water") is None and v["track_id"] not in occupied:
            out.append(Alert("medium", "vehicle_unclear", "Vehicle near the flood, water state not visible: take a closer look",
                             v["track_id"], v.get("lat"), v.get("lon"), None, False, None))
    return sorted(out, key=lambda a: PRIORITY_ORDER[a.priority])
