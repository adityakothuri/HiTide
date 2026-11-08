"""Choose a route: distinct options, each labelled with the flooding on it; never called safe."""

import networkx as nx

from critical.flood_layer import GeometryIndex
from critical.route_options import edge_statuses, nearest_node, route_options

# a ---- b ---- c   (short way, through Low Road)
#  \            /
#   d ---------    (longer way, High Road)
#    \         /
#     e ------     (longest, Ridge Road)
EDGES = {
    "a-b-0": ("Low Road", ((0.0, 0.0), (1.0, 0.0)), 100.0),
    "b-c-0": ("Low Road", ((1.0, 0.0), (2.0, 0.0)), 100.0),
    "a-d-0": ("High Road", ((0.0, 0.0), (0.5, 1.0)), 150.0),
    "d-c-0": ("High Road", ((0.5, 1.0), (2.0, 0.0)), 150.0),
    "a-e-0": ("Ridge Road", ((0.0, 0.0), (0.5, 2.0)), 300.0),
    "e-c-0": ("Ridge Road", ((0.5, 2.0), (2.0, 0.0)), 300.0),
}
INDEX = GeometryIndex({k: v[1] for k, v in EDGES.items()}, {k: v[0] for k, v in EDGES.items()})


def graph() -> nx.MultiGraph:
    g = nx.MultiGraph()
    for eid, (_name, _coords, length) in EDGES.items():
        u, v, _ = eid.split("-")
        g.add_edge(u, v, key=eid, length=length)
    return g


def test_least_flooding_first_and_the_flooded_fastest_way_last():
    status = {"a-b-0": "confirmed_flooded"}
    opts = route_options(graph(), INDEX, status, "a", "c")
    assert [o.label for o in opts] == ["Least flooding reported", "Another way", "Fastest"]
    aware, other, fastest = opts
    assert fastest.status == "flooded" and fastest.flooded == ("Low Road",)
    assert aware.via == ("High Road",) and aware.status == "clear"
    assert other.via == ("Ridge Road",)
    assert all("safe" not in str(o.public()).lower() for o in opts)


def test_when_the_fastest_way_is_dry_no_duplicate_option_is_offered():
    opts = route_options(graph(), INDEX, {}, "a", "c")
    assert opts[0].via == ("Low Road",) and opts[0].status == "clear"
    assert len({o.edge_ids for o in opts}) == len(opts)


def test_likely_flooding_is_named_and_unknown_roads_are_counted():
    opts = route_options(graph(), INDEX, {"b-c-0": "likely_flooded", "a-b-0": "unknown"}, "a", "c")
    fastest = next(o for o in opts if o.label == "Fastest")
    assert fastest.status == "likely" and fastest.likely == ("Low Road",) and fastest.unknown_roads == 1
    assert opts[0].status == "clear" and opts[-1] is fastest     # a dry way ranks above a likely-flooded one
    p = fastest.public()
    assert p["minutes"] >= 1 and p["coords"][0][0] == [0.0, 0.0]


def test_helpers_snap_points_and_merge_statuses():
    assert nearest_node(INDEX, 0.01, 0.01) == "a"
    merged = edge_statuses([{"edge_id": "a-b-0", "status": "likely_flooded"}], {"a-b-0": "cp1"}, {"cp1": "confirmed_flooded"})
    assert merged["a-b-0"] == "confirmed_flooded"


def test_parallel_directed_edges_are_the_same_road_not_a_new_option():
    g = graph()
    for eid, (_n, _c, length) in list(EDGES.items()):   # add the reverse direction of every road
        u, v, k = eid.split("-")
        g.add_edge(v, u, key=f"{v}-{u}-{k}", length=length)
    index = GeometryIndex({**INDEX.coords, **{f"{e.split('-')[1]}-{e.split('-')[0]}-0": c for e, c in INDEX.coords.items()}},
                          {**INDEX.names, **{f"{e.split('-')[1]}-{e.split('-')[0]}-0": n for e, n in INDEX.names.items()}})
    opts = route_options(g, index, {"a-b-0": "confirmed_flooded", "b-a-0": "confirmed_flooded"}, "a", "c")
    assert [o.via for o in opts] == [("High Road",), ("Ridge Road",), ("Low Road",)]   # flooded Low Road last
