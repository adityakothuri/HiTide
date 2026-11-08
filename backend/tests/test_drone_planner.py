"""Multi-drone critical-point tours: team orienteering with time-decaying value and a battery limit."""

from __future__ import annotations

import pytest

from drone.planner import DroneState, FleetProfile, Station, Target, leg, plan

STATION = Station("st", -99.14, 30.05)
FAST = FleetProfile(cruise_mps=15.0, climb_mps=4.0, agl_m=80.0, hover_s=15.0, reserve_frac=0.2, tau_s=1200.0)
OFFSET_1KM = 1000 / 111_320  # ~1 km of latitude in degrees


def _drone(i="d1", lon=-99.14, lat=30.05, battery=2100.0, busy=False):
    return DroneState(i, lon, lat, battery, busy)


def _t(pid, dlat_km, priority, deadline=None, dlon_km=0.0):
    return Target(pid, -99.14 + dlon_km * OFFSET_1KM, 30.05 + dlat_km * OFFSET_1KM, priority, deadline)


def test_visits_targets_and_returns_within_battery():
    tours = plan(0.0, [_drone()], [_t("a", 2, 10), _t("b", 3, 5)], [STATION], FAST)
    assert len(tours) == 1 and set(tours[0].stops) == {"a", "b"}
    assert tours[0].total_s <= 2100 * (1 - FAST.reserve_frac)


def test_highest_value_per_second_goes_first():
    tours = plan(0.0, [_drone()], [_t("low", 1, 1), _t("high", 1.2, 100, dlon_km=0.5)], [STATION], FAST)
    assert tours[0].stops[0] == "high"


def test_target_beyond_battery_reserve_is_skipped():
    far = _t("far", 40, 1000)  # 80 km round trip at 15 m/s ~ 89 min > 28 min usable
    tours = plan(0.0, [_drone()], [far, _t("near", 1, 1)], [STATION], FAST)
    assert tours[0].stops == ("near",)


def test_no_point_is_assigned_to_two_drones():
    west, east = _drone("w", lon=-99.20), _drone("e", lon=-99.08)
    targets = [_t("w1", 0, 10, dlon_km=-5), _t("w2", 1, 10, dlon_km=-5.5), _t("e1", 0, 10, dlon_km=5)]
    stations = [Station("sw", -99.20, 30.05), Station("se", -99.08, 30.05)]
    tours = {t.drone_id: t for t in plan(0.0, [west, east], targets, stations, FAST)}
    stops = [s for t in tours.values() for s in t.stops]
    assert sorted(stops) == ["e1", "w1", "w2"] and len(stops) == len(set(stops))
    assert set(tours["w"].stops) == {"w1", "w2"} and tours["e"].stops == ("e1",)


def test_earlier_deadline_is_checked_first_at_equal_priority():
    tours = plan(0.0, [_drone()], [_t("later", 2, 10, deadline=3000), _t("soon", 2, 10, deadline=60, dlon_km=0.3)],
                 [STATION], FAST)
    assert tours[0].stops[0] == "soon"


def test_zero_priority_and_busy_drones_get_nothing():
    assert plan(0.0, [_drone()], [_t("known", 1, 0.0)], [STATION], FAST)[0].stops == ()
    assert plan(0.0, [_drone(busy=True)], [_t("a", 1, 10)], [STATION], FAST) == ()


def test_hilly_leg_costs_climb_time_and_stays_at_constant_agl():
    a, b = (-99.14, 30.05), (-99.14, 30.05 + 3 * OFFSET_1KM)
    flat = leg(a, b, FAST, terrain=lambda lon, lat: 500.0)
    ridge = leg(a, b, FAST, terrain=lambda lon, lat: 500.0 + 120.0 * (1 - abs((lat - 30.05) / (3 * OFFSET_1KM) - 0.5) * 2))
    assert ridge.time_s > flat.time_s
    assert ridge.climb_m == pytest.approx(120.0, abs=10.0)
    assert ridge.max_agl_m == pytest.approx(FAST.agl_m)


def test_arrival_times_are_monotonic_and_value_decays_after_deadline():
    tours = plan(0.0, [_drone()], [_t("a", 2, 10, deadline=0), _t("b", 4, 10, deadline=0)], [STATION], FAST)
    t = tours[0]
    assert list(t.arrival_s) == sorted(t.arrival_s)
    assert t.value < 20.0  # both deadlines already passed, so each visit is worth less than its priority
