import pytest

from scoring.risk import RiskInput, score

BASE = dict(depth_in=0.0, rise_in_per_min=0.0, hour=14, age=40, vehicle_type="suv", situation="planning")


def s(**kw):
    return score(RiskInput(**{**BASE, **kw}))


def test_score_is_between_0_and_1():
    worst = s(depth_in=60, rise_in_per_min=10, hour=2, age=90, vehicle_type="compact", situation="stopped_in_water")
    best = s()
    assert 0.0 <= best.value <= worst.value <= 1.0


def test_deeper_water_raises_urgency():
    assert s(depth_in=20).value > s(depth_in=4).value


def test_depth_saturates_at_boat_threshold():
    assert s(depth_in=24).value == pytest.approx(s(depth_in=48).value)


def test_rising_water_raises_urgency():
    assert s(depth_in=10, rise_in_per_min=3).value > s(depth_in=10).value


def test_night_raises_urgency():
    assert s(hour=23).value > s(hour=14).value
    assert s(hour=3).value > s(hour=14).value


def test_older_driver_raises_urgency():
    assert s(age=78).value > s(age=40).value


def test_teen_driver_flagged_for_parent_notification():
    assert s(age=17).notify_parent is True
    assert s(age=40).notify_parent is False


def test_low_clearance_vehicle_raises_urgency():
    assert s(vehicle_type="compact").value > s(vehicle_type="truck").value
    assert s(vehicle_type="ev").value > s(vehicle_type="suv").value


def test_situation_order_planning_lt_driving_lt_stopped():
    assert s(situation="planning").value < s(situation="driving_toward").value < s(situation="stopped_in_water").value


def test_unknown_vehicle_uses_middle_default():
    assert 0.0 <= s(vehicle_type="spaceship").value <= 1.0


def test_reasons_explain_score():
    r = s(depth_in=20, hour=23, age=78, situation="stopped_in_water", rise_in_per_min=2)
    joined = " ".join(r.reasons)
    for word in ("20 in", "night", "older driver", "rising", "stopped"):
        assert word in joined


def test_reasons_never_expose_exact_age_or_vehicle_model():
    """Privacy: reasons go to every dashboard client, so only coarse bands, never raw personal data."""
    joined = " ".join(s(age=78, vehicle_type="compact", depth_in=10).reasons + s(age=17).reasons)
    assert "78" not in joined and "17" not in joined
    assert "compact" not in joined


def test_high_risk_flag_for_older_driver_stopped_at_night():
    assert s(depth_in=20, hour=23, age=78, situation="stopped_in_water", rise_in_per_min=2).high_risk is True
    assert s(depth_in=4, situation="planning").high_risk is False
