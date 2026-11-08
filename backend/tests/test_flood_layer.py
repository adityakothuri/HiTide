"""Phone flood layer: one map window of non-open roads (with geometry), crossings, gauges and alerts."""

import pytest

from critical.flood_layer import GeometryIndex, build_flood_layer, flood_points, flood_segments, parse_bbox

BOX = (-99.2, 30.0, -99.1, 30.1)
INDEX = GeometryIndex.from_features([
    {"properties": {"edge_id": "1-2-0", "name": "Park Street"}, "geometry": {"coordinates": [[-99.15, 30.05], [-99.14, 30.05]]}},
    {"properties": {"edge_id": "2-1-0", "name": "Park Street"}, "geometry": {"coordinates": [[-99.14, 30.05], [-99.15, 30.05]]}},
    {"properties": {"edge_id": "3-4-0", "name": "Far Road"}, "geometry": {"coordinates": [[-98.0, 31.0], [-98.1, 31.0]]}},
    {"properties": {"edge_id": "5-6-0", "name": None}, "geometry": {"coordinates": [[-99.12, 30.02], [-99.11, 30.02]]}},
])


def test_parse_bbox_accepts_a_town_window():
    assert parse_bbox("-99.2,30.0,-99.1,30.1") == BOX


@pytest.mark.parametrize("raw", ["", "1,2,3", "a,b,c,d", "-99.1,30.0,-99.2,30.1", "-99,30,-97,32", "nan,30,-99,30.1",
                                 "-200,30,-99,30.1"])
def test_parse_bbox_rejects_malformed_inverted_or_huge(raw):
    with pytest.raises(ValueError):
        parse_bbox(raw)


def test_segments_merge_both_directions_keep_the_worst_status_and_drop_open_or_outside():
    segs = [{"edge_id": "1-2-0", "status": "likely_flooded"}, {"edge_id": "2-1-0", "status": "confirmed_flooded"},
            {"edge_id": "3-4-0", "status": "confirmed_flooded"}, {"edge_id": "5-6-0", "status": "open"}]
    out = flood_segments(segs, INDEX, BOX)
    assert [(s["status"], s["name"]) for s in out] == [("confirmed_flooded", "Park Street")]
    assert sorted(out[0]["coords"]) == [[-99.15, 30.05], [-99.14, 30.05]]


def test_unnamed_roads_are_labelled_and_unknown_is_kept():
    out = flood_segments([{"edge_id": "5-6-0", "status": "unknown"}], INDEX, BOX)
    assert out[0]["name"] == "Unnamed road" and out[0]["status"] == "unknown"


def test_points_default_to_unknown_never_open():
    pts = {"cp-1": {"name": "Park St crossing", "kind": "crossing", "lon": -99.15, "lat": 30.05},
           "cp-2": {"name": "Far", "kind": "bridge", "lon": -98.0, "lat": 31.0}}
    out = flood_points(pts, {}, BOX)
    assert out == [{"id": "cp-1", "name": "Park St crossing", "kind": "crossing", "status": "unknown",
                    "lon": -99.15, "lat": 30.05}]


def test_layer_carries_time_gauges_and_alert_headlines():
    snap = {"sim_time": "2025-07-04T12:00:00+00:00", "mode": "replay", "segments": [],
            "gauges": [{"site": "08166200", "name": "Kerrville", "lon": -99.16, "lat": 30.05, "stage_ft": 30.1,
                        "flood_category": "major", "secret": "x"},
                       {"site": "far", "name": "Far", "lon": -98.0, "lat": 31.0}],
            "alerts": [{"id": "a1", "headline": "Flash Flood Emergency", "level": "emergency", "emergency": True}]}
    out = build_flood_layer(snap, {}, {}, INDEX, BOX)
    assert out["at"] == "2025-07-04T12:00:00+00:00"
    assert [g["site"] for g in out["gauges"]] == ["08166200"] and "secret" not in out["gauges"][0]
    assert out["alerts"][0]["emergency"] is True
