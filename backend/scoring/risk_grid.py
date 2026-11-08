"""Flood Risk Index surface: a relative 0..100 index per grid cell (not a water depth).

    terrain = (w_hand * hand + w_dist * dist) / (w_hand + w_dist)
    rain    = (w_r1 * rain1h + w_r24 * rain24h) / (w_r1 + w_r24)
    index   = 100 * terrain * (floor + (1 - floor) * rain)

Rain multiplies terrain susceptibility, so a dry hilltop stays near 0 however hard it rains, and a river
corridor with no rain tops out at 100 * floor. Factor indices: 0 hand, 1 dist, 2 rain1h, 3 rain24h.
Weights and constants live in config/risk_grid.yaml; the build script is scripts/build_risk_grid.py.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

FACTORS = ("hand", "dist", "rain1h", "rain24h")
TERRAIN = ("hand", "dist")
RAIN = ("rain1h", "rain24h")
NO_FACTOR = 255


def hand_risk(hand_m: np.ndarray, hand_max_m: float) -> np.ndarray:
    """1 at or below the stream surface, 0 at hand_max_m above it or higher."""
    return np.clip(1.0 - np.asarray(hand_m, dtype=float) / hand_max_m, 0.0, 1.0)


def dist_risk(dist_m: np.ndarray, scale_m: float) -> np.ndarray:
    return np.exp(-np.asarray(dist_m, dtype=float) / scale_m)


def rain_risk(inches: np.ndarray, norm_in: float) -> np.ndarray:
    return np.clip(np.asarray(inches, dtype=float) / norm_in, 0.0, 1.0)


def _group(components: Mapping[str, np.ndarray], weights: Mapping[str, float],
           keys: Sequence[str]) -> tuple[np.ndarray, list[np.ndarray]]:
    total = float(sum(weights[k] for k in keys))
    parts = [weights[k] / total * np.asarray(components[k], dtype=float) for k in keys]
    return sum(parts), parts


def combine(components: Mapping[str, np.ndarray], weights: Mapping[str, float],
            rain_floor: float) -> tuple[np.ndarray, np.ndarray]:
    """(index 0..100, contributions shaped (4, H, W) in FACTORS order). NaN in any component -> NaN."""
    terrain, t_parts = _group(components, weights, TERRAIN)
    rain, r_parts = _group(components, weights, RAIN)
    index = 100.0 * terrain * (rain_floor + (1.0 - rain_floor) * rain)
    return np.clip(index, 0.0, 100.0), np.stack(t_parts + r_parts)


def top_two(contrib: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Indices of the largest and second-largest contribution per cell; ties go to the lower index."""
    order = np.argsort(-np.nan_to_num(contrib, nan=-1.0), axis=0, kind="stable")
    return order[0].astype(np.uint8), order[1].astype(np.uint8)


def encode_frame(index: np.ndarray) -> bytes:
    """Float32 little-endian, row-major (row 0 = north)."""
    return np.ascontiguousarray(index, dtype="<f4").tobytes()


def encode_factors(top: np.ndarray, second: np.ndarray, valid: np.ndarray) -> bytes:
    packed = (top.astype(np.uint8) << 4) | (second.astype(np.uint8) & 0x0F)
    return np.where(valid, packed, NO_FACTOR).astype(np.uint8).tobytes()


def aggregate_cells(z: np.ndarray, factor: int) -> np.ndarray:
    """Block mean over factor x factor cells, ignoring NaN; ragged trailing rows/cols dropped."""
    h, w = (z.shape[0] // factor) * factor, (z.shape[1] // factor) * factor
    blocks = np.asarray(z[:h, :w], dtype=float).reshape(h // factor, factor, w // factor, factor)
    valid = ~np.isnan(blocks)
    count = valid.sum(axis=(1, 3))
    total = np.where(valid, blocks, 0.0).sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(count > 0, total / count, np.nan)


def cell_bounds(x0: float, y0: float, dx: float, dy: float, width: int,
                height: int) -> tuple[float, float, float, float]:
    """(west, south, east, north) cell-edge bounds: x0 is the left edge, y0 the top edge, dy < 0."""
    return x0, y0 + height * dy, x0 + width * dx, y0


def decode_ramp(rgba: np.ndarray, ramp: Sequence[tuple[float, str]], top_value: float) -> np.ndarray:
    """Recolored MRMS pixels -> inches. Each bin maps to its midpoint; the open top bin to top_value;
    transparent or unknown colors to 0."""
    bounds = [b for b, _ in ramp]
    values = [(bounds[i] + bounds[i + 1]) / 2 for i in range(len(bounds) - 1)] + [top_value]
    rgb = np.asarray(rgba)[..., :3].astype(np.int32)
    key = (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]
    out = np.zeros(key.shape, dtype=float)
    for (_, color), v in zip(ramp, values):
        out[key == int(color[1:7], 16)] = v
    return np.where(np.asarray(rgba)[..., 3] > 0, out, 0.0)


def forecast_rain(inches: np.ndarray, steps: int, decay_per_step: float) -> np.ndarray:
    """Persistence of the last observed rain, multiplied by decay_per_step for each step ahead."""
    return np.asarray(inches, dtype=float) * decay_per_step ** steps
