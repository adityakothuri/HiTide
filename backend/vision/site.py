"""A georeferenced filming site for real footage: lidar terrain + a mapped line + camera prior, in local metres.

Local frame: x east, y north, metres from the filmer's published position (EPSG:5070 offsets; fine over
a few hundred metres). Heights are 3DEP lidar NAVD88 metres, the same datum as the USGS gauge.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from vision.grid import GroundGrid
from vision.georef import Priors


@dataclass(frozen=True)
class Site:
    root: Path
    cfg: dict
    grid: GroundGrid             # lidar resampled to a regular local grid (y increasing with row)
    line_xy: np.ndarray          # mapped constraint line, shifted to the picked edge (local metres)
    inner_xy: np.ndarray | None  # the near edge of the same feature, when picked
    trail_xy: np.ndarray         # the mapped line itself (used as the "road" for depth)
    ground_z: float              # terrain height at the camera position

    @property
    def priors(self) -> Priors:
        return Priors(**{k: tuple(v) for k, v in self.cfg["priors"].items()})


def _offset(line: np.ndarray, d: float, away_from: np.ndarray) -> np.ndarray:
    """Shift a polyline sideways by d metres, away from a point."""
    seg = np.diff(line, axis=0)
    n = np.column_stack([-seg[:, 1], seg[:, 0]]) / np.linalg.norm(seg, axis=1, keepdims=True)
    nv = np.vstack([n[:1], (n[:-1] + n[1:]) / 2, n[-1:]])
    nv /= np.linalg.norm(nv, axis=1, keepdims=True)
    mid = line.mean(axis=0)
    if np.dot(nv.mean(axis=0), mid - away_from) < 0:
        nv = -nv
    return line + d * nv


def load_site(root: Path, half_m: float = 90.0, res_m: float = 1.0) -> Site:
    import geopandas as gpd
    from pyproj import Transformer
    from scipy.interpolate import RegularGridInterpolator

    root = Path(root)
    cfg = json.loads((root / "site.json").read_text())
    d = np.load(root / cfg["dem"])
    lat, lon = cfg["camera_latlon"]
    cx, cy = Transformer.from_crs(4326, cfg["dem_crs"], always_xy=True).transform(lon, lat)
    xs, ys, z = d["x"] - cx, d["y"] - cy, d["z"].astype(float)
    if ys[0] > ys[-1]:
        ys, z = ys[::-1], z[::-1]
    f = RegularGridInterpolator((ys, xs), z, bounds_error=False, fill_value=np.nan)
    gx = np.arange(-half_m, half_m + res_m / 2, res_m)
    gy = np.arange(-half_m, 10.0 + res_m / 2, res_m)
    yy, xx = np.meshgrid(gy, gx, indexing="ij")
    grid = GroundGrid(float(gx[0]), float(gy[0]), res_m, f(np.column_stack([yy.ravel(), xx.ravel()])).reshape(yy.shape))
    osm = gpd.read_file(root / "osm.geojson").to_crs(cfg["dem_crs"])
    named = osm[osm.get("name").astype(str).str.contains("River Trail", na=False)] if "name" in osm else osm.iloc[:0]
    geom = named.geometry.iloc[0]
    trail = np.column_stack(geom.xy) - np.array([cx, cy])
    line = _offset(trail, float(cfg.get("line_offset_m", 0.0)), np.zeros(2))
    inner = _offset(trail, -float(cfg["inner_offset_m"]), np.zeros(2)) if "inner_offset_m" in cfg else None
    ground = float(f([[0.0, 0.0]])[0])
    return Site(root, cfg, grid, line, inner, trail, ground)
