"""Area risk score (0-100) and the 'move low to high' objective."""

from __future__ import annotations

import pytest

from critical.access import Road, build_graph
from critical.area_risk import AreaInputs, area_risk, ground_label
from routing.instructions import route_out


def _a(**kw):
    base = dict(hand_m=20.0, status="ok", max_exit_p=0.02, own_road_flooded=False,
                older_share=0.0, one_story_share=0.0, cars_home_share=0.0)
    return AreaInputs(**{**base, **kw})


def test_high_ground_with_open_exits_is_low_risk():
    r = area_risk(_a())
    assert r.score < 25 and r.band == "low" and r.ground == "high"


def test_cut_off_low_ground_with_water_is_severe():
    r = area_risk(_a(hand_m=1.0, status="cut_off", max_exit_p=0.95, own_road_flooded=True, older_share=0.6))
    assert r.score >= 75 and r.band == "severe" and r.ground == "low"


def test_score_rises_monotonically_with_each_factor():
    base = area_risk(_a(hand_m=8.0, status="at_risk", max_exit_p=0.4)).score
    assert area_risk(_a(hand_m=2.0, status="at_risk", max_exit_p=0.4)).score > base          # lower ground
    assert area_risk(_a(hand_m=8.0, status="cut_off", max_exit_p=0.4)).score > base          # worse access
    assert area_risk(_a(hand_m=8.0, status="at_risk", max_exit_p=0.8)).score > base          # more water
    assert area_risk(_a(hand_m=8.0, status="at_risk", max_exit_p=0.4, older_share=1.0)).score > base


def test_factors_are_returned_and_sum_to_the_score():
    r = area_risk(_a(hand_m=3.0, status="partially_cut_off", max_exit_p=0.6, cars_home_share=1.0))
    assert set(r.factors) == {"access", "water", "ground", "vulnerability"}
    assert sum(r.factors.values()) == pytest.approx(r.score, abs=0.2)


@pytest.mark.parametrize("hand,label", [(1.0, "low"), (7.0, "mid"), (12.0, "high"), (float("inf"), "high")])
def test_ground_labels(hand, label):
    assert ground_label(hand) == label


def test_route_out_moves_people_from_low_to_high_ground():
    """The route ends at a high-ground destination, never at another low spot."""
    g = build_graph([Road("a", "home", "dip", 100), Road("b", "home", "ridge", 900)])
    elev = {"home": 480.0, "dip": 476.0, "ridge": 520.0}
    safe = {n for n, z in elev.items() if z - 476.0 >= 12.0}  # high ground only
    r = route_out(g, "home", safe, {}, {}, {"b": "Ridge Rd"})
    assert r is not None and r.edge_ids == ("b",)
