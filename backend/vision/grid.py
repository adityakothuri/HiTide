"""Ground grid around a critical point: project DEM cells into each frame, label them, vote across frames.

Voting in ground space (not image space) keeps the vote correct while the drone drifts during a hover.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from vision.camera import Intrinsics, Pose, centre, project

INVALID, OTHER, WATER, GROUND, BLOCKER = -1, 0, 1, 2, 3


@dataclass(frozen=True)
class GroundGrid:
    """Regular grid of cell centres: x = x0 + j * res, y = y0 + i * res. z is the DEM (ny, nx) in metres."""
    x0: float
    y0: float
    res: float
    z: np.ndarray

    @property
    def shape(self) -> tuple[int, int]:
        return self.z.shape

    def xy(self) -> tuple[np.ndarray, np.ndarray]:
        ny, nx = self.shape
        return np.meshgrid(self.x0 + np.arange(nx) * self.res, self.y0 + np.arange(ny) * self.res)

    def xyz(self) -> np.ndarray:
        x, y = self.xy()
        return np.column_stack([x.ravel(), y.ravel(), self.z.ravel()])

    def height_at(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Bilinear DEM height; NaN outside the grid."""
        x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
        fj, fi = (x - self.x0) / self.res, (y - self.y0) / self.res
        ny, nx = self.shape
        inside = (fj >= 0) & (fj <= nx - 1) & (fi >= 0) & (fi <= ny - 1)
        j0 = np.clip(np.floor(fj).astype(int), 0, nx - 2)
        i0 = np.clip(np.floor(fi).astype(int), 0, ny - 2)
        tj, ti = np.clip(fj - j0, 0, 1), np.clip(fi - i0, 0, 1)
        z = self.z
        h = (z[i0, j0] * (1 - tj) * (1 - ti) + z[i0, j0 + 1] * tj * (1 - ti)
             + z[i0 + 1, j0] * (1 - tj) * ti + z[i0 + 1, j0 + 1] * tj * ti)
        return np.where(inside, h, np.nan)

    def slope(self) -> np.ndarray:
        """Gradient magnitude (rise/run) per cell."""
        gy, gx = np.gradient(self.z, self.res)
        return np.hypot(gx, gy)


@dataclass(frozen=True)
class CellObs:
    """Per-cell observation. group: INVALID/OTHER/WATER/GROUND/BLOCKER. p_water NaN where not seen."""
    group: np.ndarray
    p_water: np.ndarray


@dataclass(frozen=True)
class Seg:
    """One segmented frame: ADE20K label ids (h, w) and water probability (h, w) in [0, 1]."""
    labels: np.ndarray
    p_water: np.ndarray
    low_light: bool = False
    zero_shot_frac: float = 0.0   # share of water pixels found only by the zero-shot (coarse) model


def group_lut(ids_by_group: dict[str, set[int]], n: int = 256) -> np.ndarray:
    lut = np.full(n, OTHER, dtype=np.int8)
    for name, code in (("ground", GROUND), ("blocker", BLOCKER), ("water", WATER)):
        for i in ids_by_group.get(name, ()):
            lut[i] = code
    return lut


def visible(grid: GroundGrid, pose: Pose, xyz: np.ndarray, steps: int, tol_m: float = 0.05) -> np.ndarray:
    """True where the straight line from the point to the camera clears the terrain."""
    c = centre(pose)
    # sample densely near the point, where occluding banks are; geometric spacing up to 60% of the way
    fracs = np.geomspace(1e-3, 0.6, steps)
    clear = np.ones(len(xyz), dtype=bool)
    for f in fracs:
        p = xyz + f * (c - xyz)
        h = grid.height_at(p[:, 0], p[:, 1])
        clear &= ~(h > p[:, 2] + tol_m)
    return clear


def _bilinear(img: np.ndarray, uv: np.ndarray) -> np.ndarray:
    h, w = img.shape
    u = np.clip(uv[:, 0] - 0.5, 0, w - 1.001)
    v = np.clip(uv[:, 1] - 0.5, 0, h - 1.001)
    j0, i0 = u.astype(int), v.astype(int)
    tj, ti = u - j0, v - i0
    return (img[i0, j0] * (1 - tj) * (1 - ti) + img[i0, j0 + 1] * tj * (1 - ti)
            + img[i0 + 1, j0] * (1 - tj) * ti + img[i0 + 1, j0 + 1] * tj * ti)


def label_cells(
    grid: GroundGrid, seg: Seg, cam: Intrinsics, pose: Pose, lut: np.ndarray, occlusion_steps: int = 32
) -> CellObs:
    """Project every cell centre into the frame and read its class group and water probability."""
    xyz = grid.xyz()
    uv, depth = project(cam, pose, xyz)
    h, w = seg.labels.shape
    in_frame = (depth > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)
    ok = in_frame.copy()
    ok[in_frame] = visible(grid, pose, xyz[in_frame], occlusion_steps)
    group = np.full(len(xyz), INVALID, dtype=np.int8)
    p = np.full(len(xyz), np.nan)
    uv_ok = uv[ok]
    p[ok] = _bilinear(seg.p_water.astype(float), uv_ok)
    lab = seg.labels[uv_ok[:, 1].astype(int), uv_ok[:, 0].astype(int)]
    g = lut[lab].copy()
    # the water probability decides water vs not; the argmax label decides ground vs blocker otherwise
    g[p[ok] >= 0.5] = WATER
    g[(p[ok] < 0.5) & (g == WATER)] = OTHER
    group[ok] = g
    return CellObs(group.reshape(grid.shape), p.reshape(grid.shape))


def vote(history: list[CellObs]) -> CellObs:
    """Per-cell majority of group over the frames that saw the cell; mean water probability."""
    if not history:
        raise ValueError("vote needs at least one observation")
    groups = np.stack([o.group for o in history])
    probs = np.stack([o.p_water for o in history])
    seen = groups != INVALID
    counts = np.stack([(groups == g).sum(axis=0) for g in (OTHER, WATER, GROUND, BLOCKER)])
    best = np.array([OTHER, WATER, GROUND, BLOCKER], dtype=np.int8)[counts.argmax(axis=0)]
    any_seen = seen.any(axis=0)
    group = np.where(any_seen, best, INVALID).astype(np.int8)
    n_seen = seen.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        p = np.where(any_seen, np.where(seen, probs, 0.0).sum(axis=0) / n_seen, np.nan)
    # a cell must agree with the water majority: keep p consistent with the voted group
    p = np.where(group == WATER, np.maximum(p, 0.5), np.where(group == INVALID, np.nan, np.minimum(p, 0.4999)))
    return CellObs(group, p)
