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


# ---- Simulated driver profile factors (docs/driver-profile.md) ----------------

from scoring.risk import profile_risk_fields  # noqa: E402

STOPPED = dict(depth_in=10, situation="stopped_in_water")


def test_no_profile_keeps_existing_score():
    assert s(**STOPPED, **profile_risk_fields({}, t_sim_min=0)).value == s(**STOPPED).value


def test_evacuation_need_raises_urgency_with_coarse_reason():
    r = s(**STOPPED, needs_priority=True)
    assert r.value > s(**STOPPED).value
    assert "needs extra help (self-reported)" in r.reasons
    assert "wheelchair" not in " ".join(r.reasons)


def test_new_to_area_raises_urgency():
    r = s(**STOPPED, new_to_area=True)
    assert r.value > s(**STOPPED).value
    assert "new to the area" in r.reasons


def test_distraction_history_raises_urgency_and_saturates():
    assert s(**STOPPED, distraction_per_100mi=1.0).value > s(**STOPPED).value
    assert s(**STOPPED, distraction_per_100mi=5.0).value == pytest.approx(s(**STOPPED, distraction_per_100mi=50.0).value)


def test_live_state_farm_signal_raises_urgency():
    r = s(**STOPPED, live_signals=("roadside_request",))
    assert r.value > s(**STOPPED).value
    assert "roadside help requested" in r.reasons
    assert "home water sensor alert" in s(**STOPPED, live_signals=("adt_water_sensor",)).reasons


def test_profile_factors_never_lower_urgency():
    """Rule: needs and profile data can only raise priority, never lower it."""
    base = s(**STOPPED).value
    for kw in ({"needs_priority": True}, {"new_to_area": True}, {"distraction_per_100mi": 3.0},
               {"live_signals": ("roadside_request",)}):
        assert s(**STOPPED, **kw).value >= base


def test_profile_risk_fields_reads_simulated_profile():
    profile = {
        "needs": ["wheelchair_user"],
        "household": {"new_to_area": True},
        "derived": {"distraction_per_100mi": 1.5},
        "demo_signals": [{"kind": "roadside_request", "at_min": 38}, {"kind": "adt_water_sensor", "at_min": 90}],
    }
    out = profile_risk_fields(profile, t_sim_min=40)
    assert {k: out[k] for k in ("needs_priority", "new_to_area", "distraction_per_100mi", "live_signals")} == {
        "needs_priority": True, "new_to_area": True, "distraction_per_100mi": 1.5,
        "live_signals": ("roadside_request",)}


def test_channel_only_needs_do_not_count_as_evacuation_priority():
    assert profile_risk_fields({"needs": ["hearing_loss"]}, t_sim_min=0)["needs_priority"] is False


def test_signal_not_active_before_its_time():
    out = profile_risk_fields({"demo_signals": [{"kind": "roadside_request", "at_min": 38}]}, t_sim_min=10)
    assert out["live_signals"] == ()


# ---- Baseline profile vulnerability (scoring/profile_risk.py) ----------------

def test_profile_vulnerability_raises_urgency_and_adds_reasons():
    r = s(**STOPPED, profile_vulnerability=0.8, profile_reasons=("past flood claim",))
    assert r.value > s(**STOPPED).value
    assert "past flood claim" in r.reasons


def test_zero_profile_vulnerability_keeps_old_score():
    assert s(**STOPPED, profile_vulnerability=0.0).value == s(**STOPPED).value


def test_profile_vulnerability_never_lowers_and_is_clamped():
    base = s(**STOPPED).value
    assert s(**STOPPED, profile_vulnerability=-5.0).value == base
    assert s(**STOPPED, profile_vulnerability=5.0).value == s(**STOPPED, profile_vulnerability=1.0).value


def test_duplicate_profile_reasons_collapse():
    r = s(**STOPPED, profile_reasons=("pets aboard", "pets aboard"))
    assert r.reasons.count("pets aboard") == 1


def test_profile_risk_fields_include_baseline_vulnerability():
    out = profile_risk_fields({"claims": {"past_flood_claims": [{"year": 2025}]}}, t_sim_min=0)
    assert out["profile_vulnerability"] > 0
    assert "past flood claim" in out["profile_reasons"]
    assert profile_risk_fields({}, t_sim_min=0)["profile_vulnerability"] == 0.0
