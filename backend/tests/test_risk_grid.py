"""Flood Risk Index surface (scoring/risk_grid.py): pure numpy pieces of the gridded relative index."""

from __future__ import annotations

import numpy as np
import pytest

from scoring.risk_grid import (
    aggregate_cells,
    cell_bounds,
    combine,
    decode_ramp,
    dist_risk,
    encode_factors,
    encode_frame,
    forecast_rain,
    hand_risk,
    rain_risk,
    top_two,
)

W = {"hand": 0.6, "dist": 0.4, "rain1h": 0.6, "rain24h": 0.4}
FLOOR = 0.15


def grid(v, shape=(2, 2)):
    return np.full(shape, v, dtype=float)


# --- components ---------------------------------------------------------------------------------------------

def test_hand_risk_lower_hand_is_riskier_and_clipped():
    r = hand_risk(np.array([-2.0, 0.0, 5.0, 15.0, 40.0]), hand_max_m=15.0)
    assert r.tolist() == pytest.approx([1.0, 1.0, 2 / 3, 0.0, 0.0])
    assert np.all(np.diff(r) <= 0)


def test_dist_risk_decays_with_distance():
    r = dist_risk(np.array([0.0, 400.0, 4000.0]), scale_m=400.0)
    assert r[0] == pytest.approx(1.0)
    assert r[1] == pytest.approx(np.exp(-1))
    assert r[2] < 1e-4


def test_rain_risk_normalizes_and_clips():
    assert rain_risk(np.array([0.0, 1.5, 3.0, 9.0]), norm_in=3.0).tolist() == pytest.approx([0, 0.5, 1, 1])


def test_components_propagate_nan():
    assert np.isnan(hand_risk(np.array([np.nan]), 15.0))[0]
    assert np.isnan(dist_risk(np.array([np.nan]), 400.0))[0]
    assert np.isnan(rain_risk(np.array([np.nan]), 3.0))[0]


# --- combine -----------------------------------------------------------------------------------------------

def comps(hand=0.5, dist=0.5, r1=0.5, r24=0.5):
    return {"hand": grid(hand), "dist": grid(dist), "rain1h": grid(r1), "rain24h": grid(r24)}


def test_index_monotonic_in_hand():
    lo, _ = combine(comps(hand=0.2), W, FLOOR)
    hi, _ = combine(comps(hand=0.9), W, FLOOR)
    assert np.all(hi > lo)


def test_index_monotonic_in_rain():
    lo, _ = combine(comps(r1=0.1), W, FLOOR)
    hi, _ = combine(comps(r1=0.8), W, FLOOR)
    assert np.all(hi > lo)


def test_zero_rain_caps_at_floor_share():
    idx, _ = combine(comps(hand=1.0, dist=1.0, r1=0.0, r24=0.0), W, FLOOR)
    assert np.all(idx <= 100 * FLOOR + 1e-9)
    assert idx[0, 0] == pytest.approx(100 * FLOOR)


def test_dry_hilltop_stays_low_even_in_heavy_rain():
    idx, _ = combine(comps(hand=0.0, dist=0.0, r1=1.0, r24=1.0), W, FLOOR)
    assert np.all(idx == 0.0)


def test_index_range_is_0_to_100():
    rng = np.random.default_rng(0)
    c = {k: rng.uniform(0, 1, (50, 50)) for k in W}
    idx, _ = combine(c, W, FLOOR)
    assert idx.min() >= 0.0 and idx.max() <= 100.0
    full, _ = combine(comps(1, 1, 1, 1), W, FLOOR)
    assert full[0, 0] == pytest.approx(100.0)


def test_index_nan_where_any_component_nan():
    c = comps()
    c["hand"][0, 1] = np.nan
    c["rain24h"][1, 0] = np.nan
    idx, contrib = combine(c, W, FLOOR)
    assert np.isnan(idx[0, 1]) and np.isnan(idx[1, 0])
    assert np.isfinite(idx[0, 0]) and np.isfinite(idx[1, 1])
    assert contrib.shape == (4, 2, 2)


def test_contributions_are_group_weighted_in_factor_order():
    _, contrib = combine(comps(hand=1.0, dist=1.0, r1=1.0, r24=1.0), W, FLOOR)
    assert contrib[:, 0, 0].tolist() == pytest.approx([0.6, 0.4, 0.6, 0.4])


# --- top factors ------------------------------------------------------------------------------------------

def test_top_two_picks_largest_contributions():
    contrib = np.array([0.1, 0.5, 0.3, 0.2]).reshape(4, 1, 1)
    top, second = top_two(contrib)
    assert (int(top[0, 0]), int(second[0, 0])) == (1, 2)


def test_top_two_ties_prefer_lower_index():
    top, second = top_two(np.full((4, 1, 1), 0.25))
    assert (int(top[0, 0]), int(second[0, 0])) == (0, 1)


# --- encoding ---------------------------------------------------------------------------------------------

def test_encode_frame_is_little_endian_float32_row_major():
    a = np.array([[1.0, 2.5], [np.nan, 100.0]])
    b = encode_frame(a)
    assert len(b) == 4 * 4
    back = np.frombuffer(b, dtype="<f4")
    assert back[0] == 1.0 and back[1] == 2.5 and np.isnan(back[2]) and back[3] == 100.0
    assert b[:4] == bytes([0x00, 0x00, 0x80, 0x3F])


def test_encode_factors_packs_nibbles_and_255_for_nan():
    top = np.array([[3, 0]], dtype=np.uint8)
    second = np.array([[1, 2]], dtype=np.uint8)
    valid = np.array([[True, False]])
    b = encode_factors(top, second, valid)
    assert list(b) == [(3 << 4) | 1, 255]


# --- grid helpers -----------------------------------------------------------------------------------------

def test_aggregate_cells_block_mean_and_nan():
    z = np.array([[1.0, 3.0, 5.0, 5.0, 9.0],
                  [1.0, 3.0, np.nan, np.nan, 9.0],
                  [np.nan, np.nan, 2.0, 2.0, 9.0]])
    out = aggregate_cells(z, 2)
    assert out.shape == (1, 2)  # ragged last row and column dropped
    assert out[0, 0] == pytest.approx(2.0)
    assert out[0, 1] == pytest.approx(5.0)  # NaN cells ignored inside a block
    assert np.isnan(aggregate_cells(np.full((2, 2), np.nan), 2)[0, 0])


def test_cell_bounds_edges():
    west, south, east, north = cell_bounds(x0=-99.5, y0=30.1, dx=0.001, dy=-0.002, width=300, height=100)
    assert (west, north) == (-99.5, 30.1)
    assert east == pytest.approx(-99.2)
    assert south == pytest.approx(29.9)


def test_decode_ramp_maps_colors_to_bin_values():
    ramp = [(0.01, "#a8e6a140"), (0.5, "#f4e04d"), (2.0, "#c02427")]
    rgba = np.array([[[0xa8, 0xe6, 0xa1, 0x40], [0xf4, 0xe0, 0x4d, 0xff]],
                     [[0xc0, 0x24, 0x27, 0xff], [0, 0, 0, 0]]], dtype=np.uint8)
    v = decode_ramp(rgba, ramp, top_value=3.0)
    assert v[0, 0] == pytest.approx((0.01 + 0.5) / 2)
    assert v[0, 1] == pytest.approx((0.5 + 2.0) / 2)
    assert v[1, 0] == pytest.approx(3.0)
    assert v[1, 1] == 0.0


def test_forecast_rain_decays_persistence():
    r = np.array([2.0, 0.0])
    assert forecast_rain(r, steps=1, decay_per_step=0.8).tolist() == pytest.approx([1.6, 0.0])
    assert forecast_rain(r, steps=2, decay_per_step=0.8).tolist() == pytest.approx([1.28, 0.0])
