"""HAND-style replay flood: gauge stage interpolated along a waterway with travel-time lag; truth vs belief."""

from __future__ import annotations

import numpy as np
import pytest

from sim.hand_flood import FT_TO_M, Gauge, crossing_depth_in, fill_gap, interp_rise_m, interp_rise_vec, road_depth_in

H = 3600.0


def _g(site, s_m, times_h, stage_ft, base=2.0):
    return Gauge(site, s_m, np.array(times_h, dtype=float) * H, np.array(stage_ft, dtype=float), base)


UP = _g("up", 0.0, [0, 1, 2, 3], [2, 12, 22, 12])
DOWN = _g("down", 18_000.0, [0, 1, 2, 3, 4], [2, 2, 12, 22, 12])
C = 5.0  # m/s -> 18 km = 1 h lag


def test_rise_at_a_gauge_is_its_own_reading_above_base():
    assert interp_rise_m([UP, DOWN], 0.0, 2 * H, C) == pytest.approx(20 * FT_TO_M)


def test_midway_point_blends_both_gauges_with_travel_time_lag():
    # s = 9 km: UP seen 30 min later (t - 0.5 h), DOWN seen 30 min earlier (t + 0.5 h); equal weights.
    r = interp_rise_m([UP, DOWN], 9_000.0, 2.5 * H, C)
    up = np.interp(2.0, [0, 1, 2, 3], [0, 10, 20, 10])
    down = np.interp(3.0, [0, 1, 2, 3, 4], [0, 0, 10, 20, 10])
    assert r == pytest.approx(0.5 * (up + down) * FT_TO_M)


def test_beyond_the_last_gauge_uses_the_nearest_one_shifted():
    r = interp_rise_m([UP, DOWN], 27_000.0, 3.5 * H, C)  # 9 km below DOWN -> DOWN 30 min earlier
    assert r == pytest.approx(np.interp(3.0, [0, 1, 2, 3, 4], [0, 0, 10, 20, 10]) * FT_TO_M)


def test_offline_gauge_is_unknown_in_belief_and_the_other_gauge_carries_on():
    dead = _g("dead", 0.0, [0, 1, 2], [2, 12, 30])  # stops reporting after 2 h
    assert interp_rise_m([dead], 0.0, 3 * H, C) is None
    assert interp_rise_m([dead, DOWN], 0.0, 3 * H, C) == pytest.approx(
        np.interp(2.0, [0, 1, 2, 3, 4], [0, 0, 10, 20, 10]) * FT_TO_M)


def test_fill_gap_uses_downstream_shape_scaled_to_the_last_reading():
    dead = _g("dead", 0.0, [0, 1, 2], [2, 12, 22])
    filled = fill_gap(dead, DOWN, lag_s=H, until_s=4 * H)
    assert filled.times[-1] >= 3 * H
    assert interp_rise_m([filled], 0.0, 2 * H, C) == pytest.approx(20 * FT_TO_M)  # real data untouched
    assert interp_rise_m([filled], 0.0, 3 * H, C) is not None


def test_road_depth_is_water_surface_minus_road_never_negative():
    assert road_depth_in(ref_z_m=500.0, rise_m=2.0, road_z_m=501.0) == pytest.approx(1.0 * 39.3701)
    assert road_depth_in(ref_z_m=500.0, rise_m=0.5, road_z_m=501.0) == 0.0
    assert road_depth_in(ref_z_m=500.0, rise_m=None, road_z_m=499.0) == 0.0


def test_low_water_crossing_floods_before_a_bridge():
    assert crossing_depth_in(rise_m=1.0, bridge=False) > 0
    assert crossing_depth_in(rise_m=1.0, bridge=True) == 0.0


def test_vector_interpolation_matches_scalar_including_gaps():
    dead = _g("dead", 0.0, [0, 1, 2], [2, 12, 30])
    s = np.array([0.0, 4_000.0, 9_000.0, 18_000.0, 27_000.0])
    for t in (0.5 * H, 2.5 * H, 3.5 * H, 9 * H):
        vec = interp_rise_vec([dead, DOWN], s, t, C)
        for sv, v in zip(s, vec):
            scalar = interp_rise_m([dead, DOWN], float(sv), t, C)
            assert (scalar is None and np.isnan(v)) or v == pytest.approx(scalar)


def test_fill_gap_fills_a_mid_series_outage_like_the_real_hunt_gauge():
    """Real data: Hunt dies at 05:10 CDT, then resumes ~34 h later. The fill must cover the gap, not the end."""
    hunt = _g("hunt", 0.0, [0, 1, 2, 40, 41], [2, 12, 22, 4, 3])
    filled = fill_gap(hunt, DOWN, lag_s=H, until_s=41 * H)
    assert list(filled.times) == sorted(filled.times)
    assert interp_rise_m([filled], 0.0, 3 * H, C) is not None  # inside the outage: now known (truth)
    assert interp_rise_m([filled], 0.0, 40 * H, C) == pytest.approx(2 * FT_TO_M)  # real later reading untouched


def test_belief_is_causal_never_reads_a_gauge_from_the_future():
    # A point 9 km upstream of DOWN would read DOWN 30 min ahead; a causal (belief) read must not.
    late = _g("late", 18_000.0, [0, 1, 2, 3], [2, 2, 2, 30])  # jumps at 3 h
    assert interp_rise_m([late], 9_000.0, 2.4 * H, C) > 0                 # truth: wave already passing
    assert interp_rise_m([late], 9_000.0, 2.4 * H, C, causal=True) == 0.0  # belief: only what's been reported
    vec = interp_rise_vec([late], np.array([9_000.0]), 2.4 * H, C, causal=True)
    assert vec[0] == pytest.approx(0.0)
