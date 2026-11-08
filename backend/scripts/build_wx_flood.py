"""Flood-depth frames for the ops map: the HAND-style model (sim/depth_grid.py) over a 10 m USGS 3DEP grid.

One transparent PNG per step of river rise above low flow at the Kerrville gauge (USGS 08166200), plus, per
road segment, the rise at which it becomes "likely flooded" (3 in) and "closed" (6 in). The client reads
the gauge stage at time t, converts it to a rise, and picks the frame / road status with no server call.

    cd backend && uv run python -m scripts.build_wx_flood
Writes data/town/dem10.npz (cached) and data/wx/depth/{manifest.json, rise_XX.X.png}.
"""

from __future__ import annotations

import json
import math

import numpy as np
from PIL import Image
from shapely.geometry import shape

from app.config import DATA_DIR, settings
from sim.depth_grid import depth_bands, depth_grid, river_reference
from sim.flood import M_TO_IN
from sim.hand_flood import FT_TO_M
from sim.region_flood import PRE_EVENT_END, epoch
from sim.town import load_town

TOWN_DIR = DATA_DIR / "town"
OUT = DATA_DIR / "wx" / "depth"
DEM_PATH = TOWN_DIR / "dem10.npz"
HYDRO = DATA_DIR / "region" / "hill_country" / "hydrographs_2025-07-04.json"
KERRVILLE = "08166200"

PAD_DEG = 0.004
RISE_STEP_M = 0.5
RIVER_SAMPLE_M = 3.0
M_PER_DEG_LAT = 111_320.0
LIKELY_IN, CLOSED_IN = 3.0, 6.0
# Sequential blues, light (shallow) to deep. Shown at 0.7 opacity over a dark basemap.
BAND_COLORS = ("#c6dcef", "#7fb3dc", "#3f80c0", "#1f4f96")
BAND_LABELS = ("Under 6 in", "6 to 12 in", "12 to 24 in", "Over 24 in")


def town_bounds() -> tuple[float, float, float, float]:
    fc = json.loads((TOWN_DIR / "segments.geojson").read_text())
    xs, ys = [], []
    for f in fc["features"]:
        for x, y in f["geometry"]["coordinates"]:
            xs.append(x)
            ys.append(y)
    return min(xs) - PAD_DEG, min(ys) - PAD_DEG, max(xs) + PAD_DEG, max(ys) + PAD_DEG


def load_dem(bounds: tuple[float, float, float, float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Elevation (rows north to south) and its cell-centre lon/lat axes; fetched once from 3DEP."""
    if not DEM_PATH.exists():
        import py3dep

        print("Fetching USGS 3DEP DEM (10 m)...")
        dem = py3dep.get_dem(bounds, resolution=10, crs=4326)
        if dem.rio.crs and dem.rio.crs.to_epsg() != 4326:
            dem = dem.rio.reproject("EPSG:4326")
        np.savez_compressed(DEM_PATH, z=np.asarray(dem.values, dtype=np.float32),
                            x=np.asarray(dem.x.values), y=np.asarray(dem.y.values))
    d = np.load(DEM_PATH)
    z, x, y = d["z"].astype(float), d["x"], d["y"]
    if y[0] < y[-1]:
        z, y = z[::-1], y[::-1]
    return z, x, y


def cell_index(x: np.ndarray, y: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    dx, dy = x[1] - x[0], y[1] - y[0]
    col = np.clip(np.round((lon - x[0]) / dx).astype(int), 0, x.size - 1)
    row = np.clip(np.round((lat - y[0]) / dy).astype(int), 0, y.size - 1)
    return row, col


def river_mask(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    river = shape(json.loads((TOWN_DIR / "river.geojson").read_text())["geometry"])
    lines = getattr(river, "geoms", [river])
    step_deg = RIVER_SAMPLE_M / M_PER_DEG_LAT
    pts = np.array([line.interpolate(d).coords[0] for line in lines
                    for d in np.arange(0.0, line.length, step_deg)])
    lo_x, hi_x = sorted((x[0], x[-1]))
    lo_y, hi_y = sorted((y[0], y[-1]))
    inside = (pts[:, 0] >= lo_x) & (pts[:, 0] <= hi_x) & (pts[:, 1] >= lo_y) & (pts[:, 1] <= hi_y)
    pts = pts[inside]  # clamping outside points would plant fake river cells on the edge
    mask = np.zeros((y.size, x.size), dtype=bool)
    row, col = cell_index(x, y, pts[:, 0], pts[:, 1])
    mask[row, col] = True
    return mask


def kerrville_rise() -> tuple[float, float, float]:
    """(pre-event base stage ft, max rise m, datum ft) for the Kerrville gauge, same rule as region_flood."""
    rec = json.loads(HYDRO.read_text())["gauges"][KERRVILLE]
    times = np.array([epoch(t) for t, _ in rec["series"]])
    stage = np.array([v for _, v in rec["series"]], dtype=float)
    pre = stage[times < PRE_EVENT_END]
    base = float(pre.min()) if pre.size else float(stage.min())
    return base, (float(stage.max()) - base) * FT_TO_M, float(rec["datum_ft"])


def write_frame(bands: np.ndarray, path) -> None:
    rgba = np.zeros((*bands.shape, 4), dtype=np.uint8)
    for i, hex_color in enumerate(BAND_COLORS, start=1):
        rgba[bands == i] = [int(hex_color[k:k + 2], 16) for k in (1, 3, 5)] + [255]
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)


def road_thresholds(z_ref: np.ndarray, first_wet: np.ndarray, rows: np.ndarray, cols: np.ndarray,
                    reach_m: float) -> dict[str, list[float]]:
    """edge_id -> [rise m when likely flooded, rise m when closed], for roads within reach of the river.
    A road only floods once the modelled water reaching it is connected to the river (first_wet)."""
    town = load_town()
    gap = town.elev_m - z_ref[rows, cols]
    out = {}
    for i, eid in enumerate(town.edge_ids):
        if town.river_dist_m[i] > reach_m or not np.isfinite(first_wet[i]):
            continue
        likely = max(gap[i] + LIKELY_IN / M_TO_IN, first_wet[i], 0.0)
        closed = max(gap[i] + CLOSED_IN / M_TO_IN, first_wet[i], 0.0)
        out[eid] = [round(likely, 2), round(closed, 2)]
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    bounds = town_bounds()
    dem, x, y = load_dem(bounds)
    cell_m = abs(y[1] - y[0]) * M_PER_DEG_LAT
    print(f"DEM {dem.shape}, cell ~{cell_m:.1f} m")
    river = river_mask(x, y)
    z_ref, dist = river_reference(dem, river, cell_m)
    reach_m = float(settings()["flood"]["reach_km"]) * 1000.0
    base_ft, max_rise, datum_ft = kerrville_rise()

    town = load_town()
    rows, cols = cell_index(x, y, town.midpoints[:, 0], town.midpoints[:, 1])
    first_wet = np.full(len(town.edge_ids), np.inf)
    frames = []
    for k in range(int(math.ceil(max_rise / RISE_STEP_M)) + 1):
        rise = round(k * RISE_STEP_M, 2)
        depth = depth_grid(dem, river, z_ref, dist, rise, reach_m)
        first_wet = np.where(np.isinf(first_wet) & (depth[rows, cols] > 0.0), rise, first_wet)
        bands = depth_bands(depth)
        name = f"rise_{rise:04.1f}.png"
        write_frame(bands, OUT / name)
        frames.append({"rise_m": rise, "file": name, "wet_cells": int((bands > 0).sum())})
    half_x, half_y = abs(x[1] - x[0]) / 2, abs(y[1] - y[0]) / 2
    west, east, north, south = x[0] - half_x, x[-1] + half_x, y[0] + half_y, y[-1] - half_y
    manifest = {
        "model": "HAND-style fill from the Guadalupe River over USGS 3DEP 10 m; not a hydraulic model",
        "gauge": {"site": KERRVILLE, "base_stage_ft": base_ft, "datum_ft": datum_ft},
        "rise_step_m": RISE_STEP_M,
        "coordinates": [[west, north], [east, north], [east, south], [west, south]],
        "bands": [{"label": label, "color": c} for label, c in zip(BAND_LABELS, BAND_COLORS)],
        "frames": frames,
        "roads": road_thresholds(z_ref, first_wet, rows, cols, reach_m),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, separators=(",", ":")))
    peak = frames[-1]
    print(f"{len(frames)} frames, base stage {base_ft:.2f} ft, max rise {max_rise:.2f} m, "
          f"peak wet cells {peak['wet_cells']}, roads tracked {len(manifest['roads'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
