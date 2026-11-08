"""Exit routes, exact chokepoints and truck access on the overview's worked-example network (8.2, 8.7)."""

from __future__ import annotations

from critical.access import Road, build_graph, node_access, truck_access

#  farm --- village --X1-- junction --- HWY (safe)
#              \
#               B (ranch-road ford, truck only) --- station
#  subdivision --X2-- HWY ;  subdivision --X3-- HWY2 (safe)
ROADS = [
    Road("farm-lane", "farm", "village", 900),
    Road("x1", "village", "junction", 60),
    Road("j-hwy", "junction", "HWY", 400),
    Road("ranch-1", "village", "ranch", 1500, truck_only=True),
    Road("b-ford", "ranch", "ranch2", 40, truck_only=True),
    Road("ranch-2", "ranch2", "station", 2000, truck_only=True),
    Road("x2", "subdivision", "HWY", 300),
    Road("x3", "subdivision", "HWY2", 800),
    Road("st-hwy", "station", "HWY", 3000),
]
POINT_OF = {"x1": "X1", "x2": "X2", "x3": "X3", "b-ford": "B"}
SAFE = {"HWY", "HWY2"}


def _g():
    return build_graph(ROADS)


def test_village_and_farm_depend_on_x1():
    for origin in ("village", "farm"):
        a = node_access(_g(), origin, SAFE, POINT_OF)
        assert a.status == "connected"
        assert a.unavoidable == frozenset({"X1"}) and a.optional == frozenset()


def test_subdivision_has_alternatives_so_nothing_is_unavoidable():
    a = node_access(_g(), "subdivision", SAFE, POINT_OF)
    assert a.unavoidable == frozenset()
    assert a.optional == frozenset({"X2", "X3"})
    assert len(a.routes) >= 2


def test_truck_only_roads_are_not_car_exits():
    a = node_access(_g(), "village", SAFE, POINT_OF)
    assert all("b-ford" not in r for r in a.routes)


def test_confirmed_flooded_x1_cuts_off_village():
    a = node_access(_g(), "village", SAFE, POINT_OF, removed=frozenset({"X1"}))
    assert a.status == "cut_off" and a.routes == ()


def test_losing_one_alternative_makes_the_other_unavoidable():
    a = node_access(_g(), "subdivision", SAFE, POINT_OF, removed=frozenset({"X2"}))
    assert a.status == "connected" and a.unavoidable == frozenset({"X3"})


def test_truck_access_to_cut_off_village_runs_over_the_back_road():
    t = truck_access(_g(), "village", {"station"}, POINT_OF, impassable=frozenset({"X1"}))
    assert t is not None and t.points == frozenset({"B"})


def test_no_truck_route_means_boat_required():
    t = truck_access(_g(), "village", {"station"}, POINT_OF, impassable=frozenset({"X1", "B"}))
    assert t is None


def test_unknown_origin_is_cut_off_not_an_error():
    assert node_access(_g(), "nowhere", SAFE, POINT_OF).status == "cut_off"
