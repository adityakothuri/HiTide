"""Vehicles, people, persistence, alerts and Drive Safe & Save matching (drone vision plan 7.1-7.7)."""

import numpy as np
import pytest

from vision.alerts import match_case, rules
from vision.camera import Intrinsics, Pose, project
from vision.config import vision_config
from vision.detect import Det, Persistence
from vision.grid import GroundGrid
from vision.objects import (
    Geometry, classify_person, classify_vehicle, ring_water_fraction, vehicle_band,
)

CFG = vision_config()
BANDS = CFG["vehicle_band_in"]
CAR = Det(1, "car", 0.9, (100.0, 100.0, 200.0, 140.0))


def _water(h=300, w=400, top=120):
    m = np.zeros((h, w), bool)
    m[top:] = True
    return m


# ---------- persistence ----------

def test_one_frame_detection_never_confirms_and_five_frames_do():
    p = Persistence(min_frames=5)
    flash = Det(99, "person", 0.5, (0, 0, 1, 1))
    p, confirmed = p.update([flash])
    assert confirmed == []
    for _ in range(3):
        p, confirmed = p.update([CAR])
    assert confirmed == []
    p, confirmed = p.update([CAR])
    p, confirmed = p.update([CAR])
    assert confirmed == [CAR]


def test_persistence_update_does_not_mutate_the_previous_state():
    p0 = Persistence(min_frames=2)
    p1, _ = p0.update([CAR])
    assert dict(p0.counts) == {} and dict(p1.counts) == {1: 1}


# ---------- in-water ring ----------

def test_car_surrounded_by_water_is_in_water_and_on_dry_ground_is_not():
    wet = classify_vehicle(CAR, _water(top=90), [], None, CFG)
    dry = classify_vehicle(CAR, _water(top=250), [], None, CFG)
    assert wet.in_water and not dry.in_water


def test_ring_ignores_other_detections_and_frame_edges():
    water = _water(top=0)
    other = (200.0, 100.0, 260.0, 150.0)
    assert ring_water_fraction(CAR.box, water, 0.15, [other]) == 1.0
    assert ring_water_fraction((0.0, 0.0, 400.0, 300.0), water, 0.15) is None


# ---------- vehicle location and depth (plan fix #9) ----------

def _geo(wse=1.0):
    z = np.zeros((161, 161))                     # flat ground at 0 m, 0.5 m cells, 80 m square
    return Geometry(Intrinsics.from_hfov(800, 600, 80), Pose(0, -40, 40, 0, 45), GroundGrid(-40, -40, 0.5, z), wse)


def _box_with_waterline_at(geo, xy, wse):
    uv, _ = project(geo.cam, geo.pose, np.array([[xy[0], xy[1], wse]]))
    u, v = uv[0]
    return (u - 30, v - 25, u + 30, v)


def test_vehicle_in_water_is_located_on_the_water_plane_not_behind_it():
    geo = _geo(wse=1.0)
    truth = (2.0, 10.0)
    box = _box_with_waterline_at(geo, truth, 1.0)
    water = np.zeros((600, 800), bool)
    water[int(box[3]) - 60:, :] = True
    water[int(box[1]):int(box[3]), int(box[0]):int(box[2])] = False
    v = classify_vehicle(Det(3, "car", 0.8, box), water, [], geo, CFG)
    assert v.in_water
    assert np.hypot(v.xy[0] - truth[0], v.xy[1] - truth[1]) <= 1.0
    assert v.depth_at_vehicle_in == pytest.approx(1.0 / 0.0254, rel=1e-3)
    assert v.band == "windows" and v.band_source == "water_surface"


def test_mapping_the_waterline_to_the_dem_instead_would_misplace_the_car():
    """Regression guard for the spec's 'bottom centre -> ground' mapping."""
    geo = _geo(wse=1.0)
    box = _box_with_waterline_at(geo, (2.0, 10.0), 1.0)
    from vision.camera import ray_to_plane

    on_ground = ray_to_plane(geo.cam, geo.pose, np.array([[(box[0] + box[2]) / 2, box[3]]]), 0.0)[0]
    assert np.hypot(on_ground[0] - 2.0, on_ground[1] - 10.0) > 1.0


@pytest.mark.parametrize("depth,band", [(0, "none"), (11.9, "wheels"), (12, "doors"), (23.9, "doors"),
                                        (24, "windows"), (47.9, "windows"), (48, "roof")])
def test_vehicle_bands_follow_the_spec(depth, band):
    assert vehicle_band(depth, BANDS) == band


def test_without_geometry_a_vehicle_in_water_gets_no_depth_and_no_band():
    """Depth comes only from the water edge + elevation map; the car's shape is never a ruler."""
    v = classify_vehicle(Det(1, "car", 0.9, (100, 100, 200, 121)), _water(top=60), [], None, CFG)
    assert v.in_water and v.band is None and v.band_source is None and v.depth_at_vehicle_in is None


# ---------- people (plan 7.5) ----------

def test_person_on_the_roof_of_a_car_in_water_is_on_vehicle():
    water = _water(top=90)
    car = classify_vehicle(CAR, water, [], None, CFG)
    person = Det(2, "person", 0.7, (140.0, 60.0, 160.0, 105.0))     # feet in the car's top third
    p = classify_person(person, water, [car], [CAR.box], None, None, CFG)
    assert p.situation == "on_vehicle" and p.on_vehicle_id == 1


def test_person_with_water_all_around_is_in_water():
    water = _water(top=0)
    p = classify_person(Det(2, "person", 0.6, (300.0, 150.0, 320.0, 200.0)), water, [], [], None, None, CFG)
    assert p.situation == "in_water"


def test_person_on_dry_ground_near_water_vs_far_from_it():
    water = _water(top=200)
    det = Det(2, "person", 0.6, (300.0, 40.0, 320.0, 90.0))
    assert classify_person(det, water, [], [], None, None, CFG).situation == "dry_near_water"
    assert classify_person(det, np.zeros_like(water), [], [], None, None, CFG).situation == "dry_away"


# ---------- alerts (plan 7.7) and matching (7.6) ----------

def _v(tid, depth=None, band=None, case=None, wet=True):
    return {"track_id": tid, "in_water": wet, "depth_at_vehicle_in": depth, "band": band,
            "matched_case_id": case, "lat": 30.0, "lon": -99.1}


def _p(tid, situation, on=None):
    return {"track_id": tid, "situation": situation, "on_vehicle_id": on, "lat": 30.0, "lon": -99.1}


ALERTS = CFG["alerts"]


def test_each_row_of_the_alert_table():
    assert rules([], [_p(1, "in_water")], 10, ALERTS)[0].priority == "critical"
    a = rules([_v(5, depth=30)], [_p(1, "on_vehicle", on=5)], 30, ALERTS)
    assert [x.kind for x in a] == ["person_on_vehicle"] and a[0].priority == "critical" and a[0].boat_required
    assert rules([_v(5, depth=30, case="case-001")], [], None, ALERTS)[0].kind == "vehicle_matches_case"
    assert rules([_v(5, depth=18)], [], None, ALERTS)[0].priority == "high"
    assert rules([_v(5, depth=8)], [], None, ALERTS)[0].priority == "medium"
    assert rules([], [_p(1, "dry_near_water")], None, ALERTS)[0].priority == "low"
    assert rules([], [_p(1, "dry_away")], None, ALERTS) == []
    assert rules([_v(5, depth=8, wet=False)], [], None, ALERTS) == []


def test_boat_required_threshold_is_strictly_over_24_in():
    under = rules([_v(5, depth=24)], [_p(1, "on_vehicle", on=5)], None, ALERTS)[0]
    over = rules([_v(5, depth=24.5)], [_p(1, "on_vehicle", on=5)], None, ALERTS)[0]
    assert not under.boat_required and over.boat_required


def test_unknown_depth_is_treated_conservatively():
    assert rules([_v(5)], [], None, ALERTS)[0].priority == "high"
    assert rules([_v(5)], [_p(1, "on_vehicle", on=5)], None, ALERTS)[0].boat_required


def test_a_band_without_a_measured_depth_is_never_turned_into_inches():
    a = rules([_v(5, band="windows")], [], None, ALERTS)[0]
    assert a.depth_in is None and a.priority == "high" and a.boat_required


def test_off_frame_boxes_read_nothing_instead_of_wrapping_around():
    water = _water(top=0)
    assert ring_water_fraction((-30.0, 40.0, -10.0, 60.0), water, 0.15) is None
    assert ring_water_fraction((float("nan"), 0.0, 10.0, 10.0), water, 0.15) is None


def test_alerts_are_sorted_most_urgent_first():
    a = rules([_v(5, depth=8)], [_p(1, "dry_near_water"), _p(2, "in_water")], None, ALERTS)
    assert [x.priority for x in a] == ["critical", "medium", "low"]


def test_case_match_within_50_m_only_and_ignores_resolved_cases():
    lat, lon = 30.05, -99.14
    north_49 = lat + 49 / 111_320.0
    north_51 = lat + 51 / 111_320.0
    assert match_case(lat, lon, [{"id": "case-001", "state": "calling", "lat": north_49, "lon": lon}], 50) == "case-001"
    assert match_case(lat, lon, [{"id": "case-001", "state": "calling", "lat": north_51, "lon": lon}], 50) is None
    assert match_case(lat, lon, [{"id": "case-001", "state": "resolved", "lat": lat, "lon": lon}], 50) is None
    assert match_case(None, None, [{"id": "case-001", "state": "calling", "lat": lat, "lon": lon}], 50) is None


def test_reflections_labelled_as_blockers_do_not_hide_the_water_around_a_car():
    water = _water(top=145)                      # mask says water only from just below the car
    ignore = np.zeros_like(water)
    ignore[115:145, :] = True                    # car/tree reflections around the car's lower half
    car = Det(1, "car", 0.9, (100.0, 100.0, 200.0, 140.0))
    assert ring_water_fraction(car.box, water, 0.25, ignore=ignore) == 1.0
    assert ring_water_fraction(car.box, water, 0.25) < 0.6       # without ignoring them it looked dry


def test_seated_person_on_the_roof_counts_as_on_vehicle():
    water = _water(top=90)
    car = classify_vehicle(CAR, water, [], None, CFG)
    seated = Det(2, "person", 0.7, (180.0, 78.0, 230.0, 125.0))  # hips at the roof line, legs over the glass
    assert classify_person(seated, water, [car], [CAR.box], None, None, CFG).situation == "on_vehicle"


# ---------- audit regressions (2026-11-08) ----------

def test_person_in_water_with_unknown_depth_needs_a_boat():
    assert rules([], [_p(1, "in_water")], None, ALERTS)[0].boat_required


def test_occupied_vehicle_matching_a_case_raises_one_alert_carrying_the_case():
    a = rules([_v(5, case="case-1")], [_p(1, "on_vehicle", on=5)], None, ALERTS)
    assert len(a) == 1 and a[0].kind == "person_on_vehicle" and a[0].case_id == "case-1"


def test_vehicle_and_person_without_informative_pixels_are_unknown_not_dry():
    dry = np.zeros_like(_water(top=0))
    blocked = np.ones_like(dry)                         # every ring pixel is a blocker (crowd / reflections)
    v = classify_vehicle(CAR, dry, [], None, CFG, ignore=blocked)
    assert v.in_water is None
    p = classify_person(Det(2, "person", 0.9, (300.0, 50.0, 320.0, 90.0)), np.zeros_like(dry), [], [], None, None,
                        CFG, ignore=np.ones_like(dry))
    assert p.situation == "unknown"
    kinds = {a.kind for a in rules([_v(5, wet=None)], [_p(1, "unknown")], None, ALERTS)}
    assert kinds == {"vehicle_unclear", "person_unclear"}
