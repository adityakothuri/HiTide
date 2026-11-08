"""classify_hazard: evidence -> level (pure, no region) and its invariants."""

import pytest

from safety.hazard import AheadHit, classify_hazard
from safety.levels import Level
from tests.safety_helpers import hazard, point


def lv(**kw) -> Level:
    stall = kw.pop("stall", 12.0)
    driving = kw.pop("driving", False)
    return classify_hazard(hazard(**kw), stall, driving)[0]


def test_nothing_is_none():
    assert classify_hazard(hazard(), 12.0) == (Level.NONE, ())


@pytest.mark.parametrize("depth,stall,expected", [
    (0.0, 12, Level.NONE), (2.9, 12, Level.NONE), (3.0, 12, Level.WARNING), (6.0, 12, Level.DANGER),
    (11.9, 12, Level.DANGER), (12.0, 12, Level.CRITICAL), (12.0, 24, Level.DANGER), (24.0, 24, Level.CRITICAL)])
def test_depth_on_your_road_uses_your_stall_depth(depth, stall, expected):
    assert lv(depth_in=depth, road_name="Main St", stall=stall) == expected


def test_unknown_depth_is_not_dry_and_not_flooded():
    assert lv(depth_in=None) == Level.NONE
    h = hazard(depth_in=None)
    assert h.confidence == "medium"


def test_flooded_crossing_near_is_danger_on_it_is_critical():
    assert lv(worst_point=point("likely_flooded", 300)) == Level.DANGER
    assert lv(worst_point=point("confirmed_flooded", 100, on_my_road=True)) == Level.CRITICAL
    assert lv(worst_point=point("confirmed_flooded", 100, on_my_road=False)) == Level.DANGER


def test_unknown_crossing_matters_only_under_a_warning():
    assert lv(worst_point=point("unknown", 200)) == Level.NONE
    assert lv(worst_point=point("unknown", 200), in_warning=True) == Level.WARNING
    assert lv(worst_point=point("unknown", 200), in_warning=True, in_emergency=True) == Level.DANGER


def test_warning_polygon_and_rising_gauge():
    assert lv(in_warning=True) == Level.WARNING
    assert lv(in_warning=True, gauge_rising=True, waterway="Guadalupe River") == Level.DANGER


def test_area_wide_emergency_is_danger_only_on_low_ground():
    assert lv(in_warning=True, in_emergency=True, height_above_water_m=8.0) == Level.WARNING
    assert lv(in_warning=True, in_emergency=True, height_above_water_m=2.0) == Level.DANGER
    assert lv(in_warning=True, in_emergency=True, emergency_polygon=True, height_above_water_m=8.0) == Level.DANGER


def test_high_ground_at_rest_softens_area_alerts_but_not_water_at_you():
    high = dict(height_above_water_m=20.0)
    assert lv(in_warning=True, **high) == Level.WATCH
    assert lv(in_warning=True, driving=True, **high) == Level.WARNING          # driving leaves the hill
    assert lv(worst_point=point("likely_flooded", 300), **high) == Level.WARNING  # your exits, not your house
    assert lv(depth_in=14.0, road_name="Hill Rd", **high) == Level.CRITICAL       # water at you is never softened
    assert lv(in_warning=True, far_from_water=True, height_above_water_m=None) == Level.WATCH


def test_outside_region_alerts_capped_at_warning():
    out = dict(coverage="alerts_only", height_above_water_m=None)
    assert lv(in_warning=True, **out) == Level.WARNING
    assert lv(in_warning=True, in_emergency=True, **out) == Level.WARNING
    assert lv(in_warning=True, in_emergency=True, emergency_polygon=True, **out) == Level.DANGER
    assert hazard(**out).confidence == "low"


def test_water_ahead_while_driving():
    wet = AheadHit("e1", "River Rd", 300.0, 8.0, None)
    shallow = AheadHit("e2", "Creek Rd", 300.0, 4.0, None)
    assert lv(ahead=(wet,), driving=True) == Level.DANGER
    assert lv(ahead=(shallow,), driving=True) == Level.WARNING


def test_route_with_water_is_a_warning():
    assert lv(route=(AheadHit("e1", "River Rd", 0.0, 4.0, None),)) == Level.WARNING


def test_reasons_are_worst_first():
    _, reasons = classify_hazard(hazard(in_warning=True, depth_in=13.0, road_name="Main St"), 12.0)
    assert reasons[0].startswith("About 13 in of water on Main St")


@pytest.mark.parametrize("stall", [12.0, 18.0, 24.0])
def test_monotone_in_depth(stall):
    levels = [lv(depth_in=d / 2, road_name="R", stall=stall) for d in range(0, 80)]
    assert levels == sorted(levels)


def test_monotone_in_evidence():
    """Adding evidence never lowers the level."""
    base = dict(in_warning=True)
    for extra in [dict(gauge_rising=True), dict(worst_point=point()), dict(depth_in=7.0), dict(closure_nearby="LSR"),
                  dict(in_emergency=True), dict(rain_in_hr=2.0)]:
        assert lv(**base, **extra) >= lv(**base)


def test_nws_outage_does_not_read_as_all_clear():
    blind = dict(degraded_sources=("nws_alerts",))
    assert lv(**blind) == Level.NONE                                   # nothing else going on: nothing to say
    assert lv(region_rising=True, **blind) == Level.WARNING            # creeks rising somewhere: act as warned
    assert lv(region_rising=True, worst_point=point("unknown", 200), **blind) == Level.WARNING
    assert lv(gauge_rising=True, waterway="Guadalupe River", **blind) == Level.DANGER
    assert lv(rain_in_hr=2.0, **blind) == Level.WARNING
