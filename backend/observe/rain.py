"""NOAA MRMS 1-hour radar rainfall, sampled at critical points (native 0.01 deg, about 1 km).

The statewide 0.5-degree summaries in feeds/noaa_products.py are for the map. Detection needs the value at the
crossing, so this decodes only a window around the region and reads the pixels near each point.
Negative MRMS values are sentinels (-1 no coverage, -3 missing): they become None (no evidence), never 0 (dry).
"""

from __future__ import annotations

import gzip
import math
from dataclasses import dataclass
from typing import Mapping

import numpy as np

MM_PER_IN = 25.4
NEIGHBOUR_PX = 1          # max over a 3x3 block: tolerates ~1 km of point/geolocation error
WINDOW_PAD_DEG = 0.05


@dataclass(frozen=True)
class QpeGrid:
    values: np.ndarray    # [row, col], north-up, millimetres
    west: float           # longitude of the left edge of column 0
    north: float          # latitude of the top edge of row 0
    res: float            # degrees per pixel
    valid_t: float        # product valid time, epoch s
    unit: str


def sample_points(grid: QpeGrid, points: Mapping[str, tuple[float, float]]) -> dict[str, float | None]:
    """Inches over the product's accumulation period at each (lon, lat); None where no valid pixel."""
    rows, cols = grid.values.shape
    out: dict[str, float | None] = {}
    for pid, (lon, lat) in points.items():
        r, c = math.floor((grid.north - lat) / grid.res), math.floor((lon - grid.west) / grid.res)
        if not (0 <= r < rows and 0 <= c < cols):
            out[pid] = None
            continue
        block = grid.values[max(0, r - NEIGHBOUR_PX):r + NEIGHBOUR_PX + 1, max(0, c - NEIGHBOUR_PX):c + NEIGHBOUR_PX + 1]
        good = block[np.isfinite(block) & (block >= 0)]
        out[pid] = round(float(good.max()) / MM_PER_IN, 2) if good.size else None
    return out


def decode_qpe_window(compressed: bytes, bbox: Mapping[str, float]) -> QpeGrid:
    """Decode a gzipped MRMS GRIB2 and keep only the region window. Raises ValueError on an unexpected product."""
    from rasterio.io import MemoryFile        # lazy: GDAL is only needed when live rain is on
    from rasterio.windows import from_bounds

    with MemoryFile(gzip.decompress(compressed)) as memory, memory.open() as ds:
        tags = ds.tags(1)
        unit = tags.get("GRIB_UNIT", "")
        if unit not in ("[mm]", "[mm/hr]"):
            raise ValueError(f"unexpected MRMS unit {unit!r}")
        window = from_bounds(bbox["west"] - WINDOW_PAD_DEG, bbox["south"] - WINDOW_PAD_DEG,
                             bbox["east"] + WINDOW_PAD_DEG, bbox["north"] + WINDOW_PAD_DEG,
                             ds.transform).round_offsets().round_lengths()
        values = ds.read(1, window=window).astype(float)
        tr = ds.window_transform(window)
        return QpeGrid(values=values, west=tr.c, north=tr.f, res=tr.a, valid_t=float(str(tags["GRIB_VALID_TIME"]).split()[0]), unit=unit)
