"""Flood-depth grid for the ops map, using the same HAND-style model as sim/hand_flood.py on every DEM cell.

  WSE(cell)   = z_ref(nearest river cell) + rise
  depth(cell) = max(0, WSE - ground), only within reach_m of the river and only where the wet area
                connects back to the channel (an isolated hollow behind a ridge stays dry).
Not a hydraulic model; the UI labels it as modelled.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from sim.flood import M_TO_IN

BAND_EDGES_IN = (6.0, 12.0, 24.0)
REF_SMOOTH_CELLS = 5  # low-flow surface = lowest DEM value near each river cell (the line may miss the channel)


def river_reference(dem: np.ndarray, river: np.ndarray, cell_m: float) -> tuple[np.ndarray, np.ndarray]:
    """Per cell: low-flow water surface at its nearest river cell (m), and distance to that cell (m).
    River cells over no-data ground are skipped, so a DEM edge can't hand its fill value to the surface."""
    missing = np.isnan(dem)
    usable = river & ~missing
    if not usable.any():
        return np.full(dem.shape, np.nan), np.full(dem.shape, np.inf)
    low = ndimage.minimum_filter(np.where(missing, np.inf, dem), size=REF_SMOOTH_CELLS)
    dist_cells, (iy, ix) = ndimage.distance_transform_edt(~usable, return_indices=True)
    return low[iy, ix], dist_cells * cell_m


def depth_grid(dem: np.ndarray, river: np.ndarray, z_ref: np.ndarray, dist_m: np.ndarray,
               rise_m: float, reach_m: float) -> np.ndarray:
    """Water depth in inches over each cell for a river rise of rise_m above low flow."""
    wse = z_ref + rise_m
    with np.errstate(invalid="ignore"):
        raw = np.where((dist_m <= reach_m) & ~np.isnan(dem), wse - dem, 0.0)
    wet = (raw > 0.0) | river
    labels, _ = ndimage.label(wet)
    connected = np.isin(labels, np.unique(labels[river & wet]))
    return np.where(connected, np.maximum(0.0, np.nan_to_num(raw)), 0.0) * M_TO_IN


def depth_bands(depth_in: np.ndarray) -> np.ndarray:
    """0 dry, 1 under 6 in, 2 6-12 in, 3 12-24 in, 4 24 in or more."""
    d = np.asarray(depth_in, dtype=float)
    return np.where(d > 0.0, 1 + np.searchsorted(BAND_EDGES_IN, d, side="right"), 0).astype(np.uint8)
