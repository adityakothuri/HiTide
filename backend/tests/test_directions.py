"""Where to go: a route to higher ground that avoids confirmed flooding, never called safe."""

import networkx as nx

from safety.directions import NO_ROUTE, STAY, directions_for, flooded_roads_near

COORDS = {"a-b-0": ((0.0, 0.0), (1.0, 0.0)), "b-c-0": ((1.0, 0.0), (2.0, 0.0)), "a-d-0": ((0.0, 0.0), (0.0, 1.0)),
          "d-c-0": ((0.0, 1.0), (2.0, 0.0))}
NAMES = {"a-b-0": "Park Street", "b-c-0": "Main Street", "a-d-0": "Hill Road", "d-c-0": "Ridge Drive"}


def graph() -> nx.MultiGraph:
    g = nx.MultiGraph()
    g.add_edge("a", "b", key="a-b-0", length=100.0)
    g.add_edge("b", "c", key="b-c-0", length=100.0)
    g.add_edge("a", "d", key="a-d-0", length=300.0)
    g.add_edge("d", "c", key="d-c-0", length=300.0)
    return g


def test_route_avoids_a_confirmed_flooded_crossing_and_is_never_called_safe():
    d = directions_for(graph(), {"c"}, {"a-b-0": "cp-1"}, {"cp-1": "confirmed_flooded"}, NAMES, COORDS,
                       "a-b-0", "move_to_high_ground", ("Park Street",))
    assert d.kind == "route"
    assert d.road_names == ("Hill Road", "Ridge Drive")
    assert "Avoid Park Street" in d.text and "safe" not in d.text.lower().replace("safety", "")
    assert d.coords and d.public()["coords"][0][0] == [0.0, 0.0]


def test_open_roads_take_the_short_way():
    d = directions_for(graph(), {"c"}, {}, {}, NAMES, COORDS, "a-b-0", "move_to_high_ground")
    assert d.road_names == ("Park Street", "Main Street")
    assert "0.2 km" in d.text


def test_on_high_ground_the_advice_is_to_stay():
    d = directions_for(graph(), {"c"}, {}, {}, NAMES, COORDS, "a-b-0", "stay_on_high_ground")
    assert d.kind == "stay" and d.text == STAY


def test_no_route_gives_on_foot_guidance_not_a_guess():
    g = graph()
    d = directions_for(g, {"c"}, {"a-b-0": "p", "a-d-0": "q"}, {"p": "confirmed_flooded", "q": "confirmed_flooded"},
                       NAMES, COORDS, "a-b-0", "move_to_high_ground")
    assert d.kind == "none" and d.text.startswith(NO_ROUTE)
    assert directions_for(g, {"c"}, {}, {}, NAMES, COORDS, None, "move_to_high_ground").kind == "none"


def test_flooded_roads_near_reads_worst_point_ahead_and_route_once_each():
    a = {"hazard": {"worst_point": {"name": "Park Street", "status": "confirmed_flooded"},
                    "ahead": [{"road_name": "Park Street", "point_status": "confirmed_flooded"},
                              {"road_name": "Water Street", "point_status": None, "depth_in": 12}],
                    "route": [{"road_name": "Dry Road", "point_status": "open", "depth_in": None}]}}
    assert flooded_roads_near(a) == ("Park Street", "Water Street")


def test_someone_on_a_flooded_road_is_told_to_leave_it_not_to_go_by_it():
    # Starting on Park Street (a-b): the route continues along it, then Main Street.
    d = directions_for(graph(), {"c"}, {}, {}, NAMES, COORDS, "a-b-0", "move_to_high_ground", ("Park Street",))
    assert d.text.startswith("Leave Park Street and head for higher ground by Main Street")
    assert "by Park Street" not in d.text
