"""Baseline profile vulnerability from simulated State Farm driver data (docs/driver-profile.md)."""

import re

import pytest

from app.config import settings
from scoring.profile_risk import profile_vulnerability


def pv(profile):
    return profile_vulnerability(profile)


def test_empty_profile_scores_zero():
    r = pv({})
    assert r.value == 0.0
    assert r.reasons == ()


def test_weights_sum_to_one():
    assert sum(settings()["profile_risk"]["weights"].values()) == pytest.approx(1.0)


def test_partial_profile_does_not_crash():
    assert pv({"dss": {}, "derived": {"frequent_crossings": [{}]}, "policy": None}).value == 0.0


@pytest.mark.parametrize("profile, reason", [
    ({"derived": {"frequent_crossings": [{"road": "Riverside", "trips_per_week": 14}]}},
     "drives a low-lying crossing often"),
    ({"derived": {"night_driving_share": 0.6}}, "drives often at night"),
    ({"claims": {"past_flood_claims": [{"year": 2025, "type": "vehicle_flood_total"}]}}, "past flood claim"),
    ({"dss": {"score_14d": 60}}, "risky driving pattern (Drive Safe & Save)"),
    ({"derived": {"speeding_per_100mi": 4.0}}, "risky driving pattern (Drive Safe & Save)"),
    ({"policy": {"years_licensed": 1}}, "new driver"),
    ({"dss": {"steer_clear_enrolled": True}}, "new driver"),
    ({"household": {"kids_often_aboard": True}}, "kids or dependents often aboard"),
    ({"household": {"dependents_at_home": 1}}, "kids or dependents often aboard"),
    ({"household": {"pets": True}}, "pets aboard"),
    ({"policy": {"home_type": "manufactured"}}, "lives in a manufactured home"),
    ({"dss": {"app_health": {"last_daily_signal_days_ago": 3, "location_always": True}}}, "app check-in missed"),
    ({"dss": {"app_health": {"last_daily_signal_days_ago": 0, "location_always": False}}}, "app check-in missed"),
])
def test_each_characteristic_raises_vulnerability_with_coarse_reason(profile, reason):
    r = pv(profile)
    assert r.value > 0.0
    assert reason in r.reasons


def test_good_driver_with_healthy_app_scores_zero():
    profile = {"dss": {"score_14d": 98, "app_health": {"last_daily_signal_days_ago": 0, "location_always": True}},
               "derived": {"speeding_per_100mi": 0.0, "night_driving_share": 0.0, "frequent_crossings": []},
               "policy": {"years_licensed": 20, "home_type": "house"}, "household": {"pets": False}}
    assert pv(profile).value == 0.0


def test_crossing_exposure_saturates():
    few = pv({"derived": {"frequent_crossings": [{"trips_per_week": 3}]}}).value
    many = pv({"derived": {"frequent_crossings": [{"trips_per_week": 14}, {"trips_per_week": 14}]}}).value
    more = pv({"derived": {"frequent_crossings": [{"trips_per_week": 40}]}}).value
    assert 0 < few < many == pytest.approx(more)


def test_more_characteristics_never_lower_vulnerability():
    one = pv({"claims": {"past_flood_claims": [{"year": 2025}]}}).value
    two = pv({"claims": {"past_flood_claims": [{"year": 2025}]}, "household": {"pets": True}}).value
    assert two >= one


def test_score_stays_in_unit_range_for_worst_case():
    worst = {"derived": {"frequent_crossings": [{"trips_per_week": 50}], "night_driving_share": 1.0,
                         "speeding_per_100mi": 20},
             "claims": {"past_flood_claims": [{"year": 2025}]}, "dss": {"score_14d": 0, "steer_clear_enrolled": True,
                                                                         "app_health": {"location_always": False}},
             "policy": {"years_licensed": 0, "home_type": "manufactured"},
             "household": {"kids_often_aboard": True, "pets": True, "dependents_at_home": 2}}
    assert pv(worst).value == pytest.approx(1.0)


def test_reasons_are_coarse():
    """No exact scores, counts, or road names leak into reasons."""
    r = pv({"derived": {"frequent_crossings": [{"road": "Riverside Drive", "trips_per_week": 9}],
                        "night_driving_share": 0.6},
            "dss": {"score_14d": 55}, "claims": {"past_flood_claims": [{"year": 2025}]}})
    text = " ".join(r.reasons)
    assert not re.search(r"\d", text.replace("Drive Safe & Save", ""))
    assert "Riverside" not in text
