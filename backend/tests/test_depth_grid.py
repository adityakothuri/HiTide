"""Flood-depth grid for the ops map: HAND-style fill from the river, connected to the channel only."""

from __future__ import annotations

import numpy as np
import pytest

from sim.depth_grid import BAND_EDGES_IN, depth_bands, depth_grid, river_reference
from sim.flood import M_TO_IN

CELL = 10.0  # m


def _valley() -> tuple[np.ndarray, np.ndarray]:
    """5 x 9 grid: river down column 4 at 100 m, ground rising 1 m per cell away from it."""
    cols = np.abs(np.arange(9) - 4).astype(float)
    dem = np.tile(100.0 + cols, (5, 1))
    river = np.zeros_like(dem, dtype=bool)
    river[:, 4] = True
    return dem, river


def test_reference_is_the_river_surface_and_distance_grows_from_it():
    dem, river = _valley()
    z_ref, dist = river_reference(dem, river, CELL)
    assert np.allclose(z_ref, 100.0)
    assert dist[0, 4] == 0.0
    assert dist[0, 6] == pytest.approx(2 * CELL)


def test_ground_below_the_raised_surface_is_wet_by_the_difference():
    dem, river = _valley()
    z_ref, dist = river_reference(dem, river, CELL)
    d = depth_grid(dem, river, z_ref, dist, rise_m=2.5, reach_m=1_000.0)
    assert d[2, 4] == pytest.approx(2.5 * M_TO_IN)
    assert d[2, 5] == pytest.approx(1.5 * M_TO_IN)
    assert d[2, 7] == 0.0  # 3 m above the river, rise is 2.5 m


def test_a_low_pit_not_connected_to_the_river_stays_dry():
    dem, river = _valley()
    dem[2, 0] = 95.0  # far-side hollow, ridge (cells 1-3) between it and the river
    dem[2, 1] = 104.0
    z_ref, dist = river_reference(dem, river, CELL)
    d = depth_grid(dem, river, z_ref, dist, rise_m=2.0, reach_m=1_000.0)
    assert d[2, 0] == 0.0


def test_cells_beyond_reach_stay_dry():
    dem, river = _valley()
    dem[:, 8] = 100.0  # low, connected only by distance
    dem[:, 5:8] = 100.0
    z_ref, dist = river_reference(dem, river, CELL)
    d = depth_grid(dem, river, z_ref, dist, rise_m=1.0, reach_m=25.0)
    assert d[0, 6] > 0.0
    assert d[0, 8] == 0.0


def test_depth_never_falls_as_the_river_rises():
    dem, river = _valley()
    z_ref, dist = river_reference(dem, river, CELL)
    lo = depth_grid(dem, river, z_ref, dist, rise_m=1.0, reach_m=1_000.0)
    hi = depth_grid(dem, river, z_ref, dist, rise_m=3.0, reach_m=1_000.0)
    assert np.all(hi >= lo)


def test_bands_split_at_6_12_24_inches_and_zero_is_dry():
    assert BAND_EDGES_IN == (6.0, 12.0, 24.0)
    d = np.array([0.0, 0.5, 5.99, 6.0, 11.9, 12.0, 23.9, 24.0, 80.0])
    assert depth_bands(d).tolist() == [0, 1, 1, 2, 2, 3, 3, 4, 4]


def test_nan_ground_is_dry():
    dem, river = _valley()
    dem[0, 5] = np.nan
    z_ref, dist = river_reference(dem, river, CELL)
    d = depth_grid(dem, river, z_ref, dist, rise_m=3.0, reach_m=1_000.0)
    assert d[0, 5] == 0.0
    assert not np.isnan(d).any()


def test_river_cells_over_missing_ground_do_not_set_the_surface():
    dem, river = _valley()
    dem[:, 3:6] = np.nan  # the river runs off the DEM's no-data edge here
    dem[0, 4] = 100.0
    dem[1:, 0:3] = 103.0
    z_ref, dist = river_reference(dem, river, CELL)
    assert np.nanmax(z_ref) == pytest.approx(100.0)
    d = depth_grid(dem, river, z_ref, dist, rise_m=1.0, reach_m=1_000.0)
    assert d[3, 1] == 0.0  # 103 m ground stays dry with a 101 m surface
