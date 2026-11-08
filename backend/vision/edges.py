"""Water edge points: where water physically meets open ground (drone vision plan 5.1-5.2).

Works on the voted ground grid. A boundary between a WATER cell and a GROUND cell is kept only if the
dry side is mostly open ground for a few cells (not tree, building, car, frame border or unseen). The
crossing is refined to sub-cell precision by searching the latest frame's water probability for its
0.5 crossing along the boundary pair (image resolution is usually finer than the grid).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from vision.camera import Intrinsics, Pose, project
from vision.geom import densify
from vision.grid import GROUND, WATER, CellObs, GroundGrid, Seg, _bilinear


@dataclass(frozen=True)
class RoadGeom:
    """Road centreline through the critical point (metres) and half width."""
    centreline: np.ndarray
    half_width_m: float

    def samples(self, step: float) -> np.ndarray:
        return densify(self.centreline, step)

    def low_point_and_axis(self, grid: GroundGrid) -> tuple[np.ndarray, np.ndarray, float]:
        """Lowest centreline point inside the grid, the local road direction there, and its height."""
        pts = self.samples(grid.res / 2)
        z = grid.height_at(pts[:, 0], pts[:, 1])
        if np.all(np.isnan(z)):
            raise ValueError("road centreline does not cross the grid")
        k = int(np.nanargmin(z))
        a, b = pts[max(0, k - 4)], pts[min(len(pts) - 1, k + 4)]
        axis = (b - a) / max(np.linalg.norm(b - a), 1e-9)
        return pts[k], axis, float(z[k])


@dataclass(frozen=True)
class EdgeSet:
    xy: np.ndarray       # (n, 2)
    z: np.ndarray        # (n,) DEM height at the crossing
    side: np.ndarray     # (n,) -1 / +1: which bank (by water->ground facing, see bank_sides)
    slope: np.ndarray    # (n,) terrain slope at the crossing

    def __len__(self) -> int:
        return len(self.z)

    @staticmethod
    def empty() -> "EdgeSet":
        e = np.zeros(0)
        return EdgeSet(np.zeros((0, 2)), e, e.astype(int), e)


def _pairs(group: np.ndarray, window: int, ground_frac: float) -> list[tuple[np.ndarray, np.ndarray, int, int]]:
    """(water cell idx, ground cell idx, di, dj) for every 4-neighbour boundary with an open dry side."""
    ny, nx = group.shape
    out = []
    for di, dj in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        wi, wj = np.nonzero(group == WATER)
        gi, gj = wi + di, wj + dj
        ok = (gi >= 0) & (gi < ny) & (gj >= 0) & (gj < nx)
        wi, wj, gi, gj = wi[ok], wj[ok], gi[ok], gj[ok]
        ok = group[gi, gj] == GROUND
        wi, wj, gi, gj = wi[ok], wj[ok], gi[ok], gj[ok]
        # dry-side window: the next `window` cells beyond the ground cell must be mostly GROUND (and on grid)
        good = np.zeros(len(gi), dtype=float)
        for k in range(1, window + 1):
            ki, kj = gi + k * di, gj + k * dj
            inside = (ki >= 0) & (ki < ny) & (kj >= 0) & (kj < nx)
            vals = np.where(inside, group[np.clip(ki, 0, ny - 1), np.clip(kj, 0, nx - 1)], -9)
            good += vals == GROUND
        keep = good / max(window, 1) >= ground_frac
        # the water side must also be real water for one more cell (not a one-cell sliver at a blocker)
        bi, bj = wi - di, wj - dj
        inside = (bi >= 0) & (bi < ny) & (bj >= 0) & (bj < nx)
        keep &= inside & (group[np.clip(bi, 0, ny - 1), np.clip(bj, 0, nx - 1)] == WATER)
        out.append(((wi[keep], wj[keep]), (gi[keep], gj[keep]), di, dj))
    return out


def _refine(
    grid: GroundGrid, a_xy: np.ndarray, b_xy: np.ndarray, p_a: np.ndarray, p_b: np.ndarray,
    seg: Seg | None, cam: Intrinsics | None, pose: Pose | None, samples: int,
) -> np.ndarray:
    """Fraction t in [0, 1] from water cell a to ground cell b where p_water crosses 0.5."""
    with np.errstate(invalid="ignore", divide="ignore"):
        t_cell = np.clip((p_a - 0.5) / (p_a - p_b), 0, 1)
    t_cell = np.where(np.isfinite(t_cell), t_cell, 0.5)
    if seg is None or cam is None or pose is None or len(a_xy) == 0:
        return t_cell
    ts = np.linspace(0, 1, samples)
    xy = a_xy[:, None, :] + ts[None, :, None] * (b_xy - a_xy)[:, None, :]
    flat = xy.reshape(-1, 2)
    z = grid.height_at(flat[:, 0], flat[:, 1])
    uv, depth = project(cam, pose, np.column_stack([flat, z]))
    h, w = seg.p_water.shape
    ok = (depth > 0) & np.isfinite(uv).all(axis=1) & (uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)
    p = np.full(len(flat), np.nan)
    p[ok] = _bilinear(seg.p_water.astype(float), uv[ok])
    p = p.reshape(len(a_xy), samples)
    t_out = t_cell.copy()
    found = np.zeros(len(a_xy), dtype=bool)
    for k in range(samples - 1):
        p0, p1 = p[:, k], p[:, k + 1]
        cross = (p0 >= 0.5) & (p1 < 0.5) & np.isfinite(p0) & np.isfinite(p1) & ~found
        frac = (p0 - 0.5) / np.where(p0 - p1 == 0, 1, p0 - p1)
        t_out = np.where(cross, ts[k] + frac * (ts[k + 1] - ts[k]), t_out)
        found |= cross                              # keep the first crossing from the water side
    return t_out


def extract_edges(
    obs: CellObs, grid: GroundGrid, road: RoadGeom, *, window: int = 2, ground_frac: float = 0.6,
    seg: Seg | None = None, cam: Intrinsics | None = None, pose: Pose | None = None, samples: int = 9,
) -> EdgeSet:
    x, y = grid.xy()
    slope = grid.slope()
    xs, zs, sides, slopes = [], [], [], []
    for (wi, wj), (gi, gj), _, _ in _pairs(obs.group, window, ground_frac):
        if len(wi) == 0:
            continue
        a = np.column_stack([x[wi, wj], y[wi, wj]])
        b = np.column_stack([x[gi, gj], y[gi, gj]])
        t = _refine(grid, a, b, obs.p_water[wi, wj], obs.p_water[gi, gj], seg, cam, pose, samples)
        pts = a + t[:, None] * (b - a)
        xs.append(pts)
        zs.append(grid.height_at(pts[:, 0], pts[:, 1]))
        sides.append(b - a)                         # water -> ground facing; turned into a bank below
        slopes.append((slope[wi, wj] + slope[gi, gj]) / 2)
    if not xs:
        return EdgeSet.empty()
    z = np.concatenate(zs)
    ok = np.isfinite(z)
    return EdgeSet(np.concatenate(xs)[ok], z[ok], bank_sides(np.concatenate(sides)[ok]), np.concatenate(slopes)[ok])


def bank_sides(facing: np.ndarray) -> np.ndarray:
    """Which bank each edge is on (+1/-1), from its water->ground direction.

    Opposite banks face opposite ways, so the sign along the dominant facing axis separates them, whatever
    the road's direction (a road along the river would otherwise have 'two sides' on a single bank).
    """
    if len(facing) == 0:
        return np.zeros(0, dtype=int)
    d = facing / np.maximum(np.linalg.norm(facing, axis=1, keepdims=True), 1e-9)
    _, vecs = np.linalg.eigh(d.T @ d)
    n = vecs[:, -1]
    return np.where(d @ n >= 0, 1, -1)
