"""Simulated flash flood: river water surface rises over time and spreads to nearby low roads.

depth over a road = water surface elevation at that road minus road elevation (never negative).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

M_TO_IN = 39.3701


@dataclass(frozen=True)
class FloodParams:
    base_wse_m: float
    rise_m_per_min: float
    max_rise_m: float
    decay_m_per_km: float
    reach_km: float


def river_wse(t_sim_s: float, p: FloodParams) -> float:
    rise = min(p.max_rise_m, p.rise_m_per_min * max(0.0, t_sim_s) / 60.0)
    return p.base_wse_m + rise


def wse_at(dist_m: np.ndarray, river_wse_m: float, p: FloodParams) -> np.ndarray:
    dist_km = np.asarray(dist_m, dtype=float) / 1000.0
    wse = river_wse_m - p.decay_m_per_km * dist_km
    return np.where(dist_km > p.reach_km, -np.inf, wse)


def depth_in(wse_m: np.ndarray, road_elev_m: np.ndarray) -> np.ndarray:
    diff = np.asarray(wse_m, dtype=float) - np.asarray(road_elev_m, dtype=float)
    diff = np.nan_to_num(diff, nan=0.0, neginf=0.0, posinf=0.0)
    return np.maximum(0.0, diff) * M_TO_IN
