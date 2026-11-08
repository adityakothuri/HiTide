"""Tabletop print scale and CAD ground truth for the 3D-printed Kerrville flood model.

Three frames:
  world  - real metres (x east / y north from the crop origin, z = NAVD88 elevation)
  model  - the physical print in millimetres; horizontal = world * mm_per_m,
           height = base_mm + (z_world - z_datum) * exaggeration * mm_per_m
  ex     - "exaggerated world": the model divided uniformly by mm_per_m (metres). Uniform, so camera
           geometry measured on the table stays valid; heights carry the exaggeration until world_from_ex.

Real water in a tray is level, so the ground-truth flood at a given water level is a bathtub fill of the
CAD heightmap, connected to the river channel (a sealed hollow stays dry until the water overtops it).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

MM3_PER_ML = 1000.0


@dataclass(frozen=True)
class PrintScale:
    mm_per_m: float        # horizontal: model mm per world metre
    exaggeration: float    # vertical exaggeration factor
    z_datum_m: float       # world elevation printed at base_mm
    base_mm: float         # height of the datum above the print bed

    def __post_init__(self) -> None:
        if self.mm_per_m <= 0 or self.exaggeration <= 0:
            raise ValueError("mm_per_m and exaggeration must be positive")

    @property
    def vertical_mm_per_m(self) -> float:
        return self.mm_per_m * self.exaggeration

    def model_mm(self, z_world_m):
        return self.base_mm + (np.asarray(z_world_m, dtype=float) - self.z_datum_m) * self.vertical_mm_per_m

    def world_m(self, h_mm):
        return self.z_datum_m + (np.asarray(h_mm, dtype=float) - self.base_mm) / self.vertical_mm_per_m

    def ex_m(self, mm):
        """Model millimetres (any axis) -> exaggerated-world metres."""
        return np.asarray(mm, dtype=float) / self.mm_per_m

    def world_from_ex(self, z_ex_m):
        return self.world_m(np.asarray(z_ex_m, dtype=float) * self.mm_per_m)

    def rise_m(self, level_mm: float, zref_world_m: float) -> float:
        """World rise above the low-flow surface for a water level measured on the print."""
        return float(self.world_m(level_mm) - zref_world_m)

    def level_mm(self, rise_m: float, zref_world_m: float) -> float:
        return float(self.model_mm(zref_world_m + rise_m))


def bathtub_wet(height_mm: np.ndarray, level_mm: float, seed: np.ndarray) -> np.ndarray:
    """Cells under a level water surface that connect (4-neighbour) to the seed (river channel)."""
    below = np.asarray(height_mm) < level_mm
    labels, _ = ndimage.label(below)
    keep = np.unique(labels[seed & below])
    return np.isin(labels, keep[keep > 0])


def volume_ml(height_mm: np.ndarray, level_mm: float, seed: np.ndarray, cell_mm: float) -> float:
    wet = bathtub_wet(height_mm, level_mm, seed)
    depth = np.where(wet, level_mm - height_mm, 0.0)
    return float(depth.sum() * cell_mm * cell_mm / MM3_PER_ML)


def volume_curve(height_mm: np.ndarray, levels_mm, seed: np.ndarray, cell_mm: float) -> list[tuple[float, float]]:
    """(level_mm, cumulative pour mL) pairs, ascending."""
    return [(float(lv), volume_ml(height_mm, float(lv), seed, cell_mm)) for lv in sorted(levels_mm)]


def level_for_volume(curve: list[tuple[float, float]], poured_ml: float) -> float:
    """Invert the pour table: the water level after pouring poured_ml into the empty basin."""
    levels = np.array([lv for lv, _ in curve])
    vols = np.array([v for _, v in curve])
    if not vols[0] <= poured_ml <= vols[-1]:
        raise ValueError(f"{poured_ml} mL is outside the pour table ({vols[0]:.1f}-{vols[-1]:.1f} mL)")
    return float(np.interp(poured_ml, vols, levels))
