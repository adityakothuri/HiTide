from __future__ import annotations

import pytest

from stages.stop_detect import is_stopped_in_water

BASE = dict(
    speed_mps=0.0,
    stationary_for_s=60.0,
    dist_to_nearest_dest_m=200.0,
    depth_in=6.0,
    stop_seconds=60.0,
    dest_radius_m=75.0,
)


def check(**overrides: float) -> bool:
    return is_stopped_in_water(**{**BASE, **overrides})


def test_all_conditions_met():
    assert check() is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"speed_mps": 0.5},  # speed must be strictly < 0.5
        {"speed_mps": 3.0},
        {"stationary_for_s": 59.9},
        {"dist_to_nearest_dest_m": 75.0},  # must be strictly > radius
        {"dist_to_nearest_dest_m": 10.0},
        {"depth_in": 2.9},
    ],
)
def test_each_condition_failing_alone(overrides):
    assert check(**overrides) is False


def test_speed_just_under_threshold():
    assert check(speed_mps=0.49) is True


def test_stationary_boundary_inclusive():
    assert check(stationary_for_s=60.0) is True
    assert check(stationary_for_s=60.1) is True


def test_distance_just_over_radius():
    assert check(dist_to_nearest_dest_m=75.01) is True


def test_depth_boundary_inclusive_at_default_caution():
    assert check(depth_in=3.0) is True


def test_custom_caution_threshold():
    assert check(depth_in=5.0, caution_in=6.0) is False
    assert check(depth_in=6.0, caution_in=6.0) is True


def test_custom_stop_seconds_and_radius():
    assert check(stationary_for_s=10.0, stop_seconds=10.0) is True
    assert check(dist_to_nearest_dest_m=100.0, dest_radius_m=150.0) is False


def test_returns_plain_bool():
    assert isinstance(check(), bool)
