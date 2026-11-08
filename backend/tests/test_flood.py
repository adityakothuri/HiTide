import numpy as np
import pytest

from sim.flood import FloodParams, depth_in, river_wse, wse_at

P = FloodParams(base_wse_m=480.0, rise_m_per_min=0.1, max_rise_m=3.0, decay_m_per_km=2.0, reach_km=1.0)


def test_river_wse_starts_at_base():
    assert river_wse(0, P) == pytest.approx(480.0)


def test_river_wse_rises_linearly_with_sim_minutes():
    assert river_wse(600, P) == pytest.approx(481.0)  # 10 min * 0.1 m/min


def test_river_wse_caps_at_max_rise():
    assert river_wse(10_000, P) == pytest.approx(483.0)


def test_wse_decays_with_distance_from_river():
    wse = wse_at(np.array([0.0, 500.0]), 482.0, P)
    assert wse[0] == pytest.approx(482.0)
    assert wse[1] == pytest.approx(481.0)  # 0.5 km * 2 m/km


def test_wse_beyond_reach_never_floods():
    wse = wse_at(np.array([1500.0]), 482.0, P)
    assert np.isneginf(wse[0])


def test_depth_is_water_surface_minus_road_in_inches():
    d = depth_in(np.array([481.0]), np.array([480.0]))
    assert d[0] == pytest.approx(39.37, rel=1e-3)


def test_depth_never_negative_and_nan_safe():
    d = depth_in(np.array([479.0, -np.inf, 481.0]), np.array([480.0, 400.0, np.nan]))
    assert list(d) == [0.0, 0.0, 0.0]


def test_rising_water_floods_more_roads_over_time():
    dist = np.array([0.0, 200.0, 800.0])
    elev = np.array([480.5, 481.0, 482.0])
    early = depth_in(wse_at(dist, river_wse(300, P), P), elev)
    late = depth_in(wse_at(dist, river_wse(1800, P), P), elev)
    assert (late > 0).sum() > (early > 0).sum()
