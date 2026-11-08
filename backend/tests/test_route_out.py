"""Route-out penalties (overview.md 10.2) and safety wording (10.3)."""

from __future__ import annotations

from critical.access import Road, build_graph
from routing.instructions import TURN_AROUND, route_message, route_out

#  home --x-- safe (short, via a floodable point)   home --long-- safe (dry, 10x longer)
G = build_graph([Road("short", "home", "safe", 100), Road("long-a", "home", "mid", 500), Road("long-b", "mid", "safe", 500)])
POINT_OF = {"short": "X"}
NAMES = {"short": "Low Water Rd", "long-a": "Ridge Rd", "long-b": "Highway 39"}


def _route(status):
    return route_out(G, "home", {"safe"}, POINT_OF, {"X": status}, NAMES)


def test_open_crossing_is_used():
    assert _route("open").edge_ids == ("short",)


def test_unknown_x3_still_shorter_than_detour():
    assert _route("unknown").edge_ids == ("short",)


def test_likely_flooded_x50_takes_the_dry_detour():
    r = _route("likely_flooded")
    assert r.edge_ids == ("long-a", "long-b") and r.road_names == ("Ridge Rd", "Highway 39")


def test_confirmed_flooded_is_removed_and_no_path_means_none():
    g = build_graph([Road("short", "home", "safe", 100)])
    assert route_out(g, "home", {"safe"}, POINT_OF, {"X": "confirmed_flooded"}, NAMES) is None


def test_message_never_says_safe_road_and_ends_with_turn_around():
    msg = route_message("Kerrville homes", _route("likely_flooded"))
    assert "avoids known flooding" in msg and TURN_AROUND in msg
    assert "safe road" not in msg.lower() and "road is safe" not in msg.lower()
