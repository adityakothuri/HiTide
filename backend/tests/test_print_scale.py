"""Tabletop print scale and CAD ground truth: model mm <-> world m, bathtub fill, pour volume."""

import numpy as np
import pytest

from sim.print_scale import PrintScale, bathtub_wet, level_for_volume, volume_curve, volume_ml


@pytest.fixture
def scale() -> PrintScale:
    # 220 mm across 1200 m, 3x vertical, datum 480 m printed 4 mm above the bed
    return PrintScale(mm_per_m=220 / 1200, exaggeration=3.0, z_datum_m=480.0, base_mm=4.0)


def test_world_height_maps_to_model_mm_with_exaggeration(scale):
    assert scale.model_mm(480.0) == pytest.approx(4.0)
    assert scale.model_mm(490.0) == pytest.approx(4.0 + 10 * 3 * 220 / 1200)


def test_model_mm_round_trips_to_world(scale):
    z = np.array([475.0, 500.0, 533.3])
    assert np.allclose(scale.world_m(scale.model_mm(z)), z)


def test_exaggerated_frame_is_a_uniform_scale_of_the_table(scale):
    # x and z both divide by mm_per_m, so camera geometry measured on the table is preserved
    assert scale.ex_m(scale.mm_per_m * 1000) == pytest.approx(1000.0)
    assert scale.world_from_ex(scale.ex_m(scale.model_mm(512.0))) == pytest.approx(512.0)


def test_rise_from_water_level(scale):
    zref = 490.0
    level = scale.model_mm(zref + 6.0)
    assert scale.rise_m(level, zref) == pytest.approx(6.0)
    assert scale.level_mm(6.0, zref) == pytest.approx(level)


def test_invalid_scale_rejected():
    with pytest.raises(ValueError):
        PrintScale(mm_per_m=0.0, exaggeration=3.0, z_datum_m=0.0, base_mm=4.0)
    with pytest.raises(ValueError):
        PrintScale(mm_per_m=0.2, exaggeration=-1.0, z_datum_m=0.0, base_mm=4.0)


def _two_basins() -> tuple[np.ndarray, np.ndarray]:
    """10 x 10 mm cells: a channel at 2 mm on the left, a sealed hollow at 1 mm behind a 5 mm ridge."""
    h = np.full((5, 9), 6.0)
    h[:, 0:3] = 2.0          # channel (connected to the river seed)
    h[:, 3] = 5.0            # ridge
    h[1:4, 4:8] = 1.0        # isolated hollow, against the ridge
    seed = np.zeros_like(h, dtype=bool)
    seed[:, 0] = True
    return h, seed


def test_bathtub_fills_only_cells_connected_to_the_river():
    h, seed = _two_basins()
    wet = bathtub_wet(h, 3.0, seed)
    assert wet[:, 0:3].all()
    assert not wet[:, 3:].any()      # the hollow is lower but sealed off


def test_bathtub_overtops_the_ridge():
    h, seed = _two_basins()
    wet = bathtub_wet(h, 5.5, seed)
    assert wet[2, 6]                 # water spilled over the 5 mm ridge into the hollow


def test_volume_is_depth_times_cell_area_over_wet_cells():
    h, seed = _two_basins()
    # 15 channel cells x 1 mm deep x 100 mm2 = 1500 mm3 = 1.5 mL
    assert volume_ml(h, 3.0, seed, cell_mm=10.0) == pytest.approx(1.5)


def test_volume_curve_is_monotonic_and_inverts():
    h, seed = _two_basins()
    levels = np.arange(2.0, 6.01, 0.25)
    curve = volume_curve(h, levels, seed, cell_mm=10.0)
    vols = np.array([v for _, v in curve])
    assert np.all(np.diff(vols) >= 0)
    assert level_for_volume(curve, volume_ml(h, 3.4, seed, cell_mm=10.0)) == pytest.approx(3.4, abs=0.05)


def test_level_for_volume_rejects_out_of_range():
    curve = [(2.0, 0.0), (3.0, 1.5)]
    with pytest.raises(ValueError):
        level_for_volume(curve, 9.0)
