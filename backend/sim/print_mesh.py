"""Printable meshes for the tabletop model: watertight heightfield, road ribbons, building boxes, binary STL.

All coordinates are model millimetres (x east, y north, z up). Triangles are (n, 3, 3) float arrays with
counter-clockwise winding seen from outside, so normals point out.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np

STL_HEADER = b"FloodWatch tabletop model (model mm)".ljust(80, b" ")


def heightfield_solid(h: np.ndarray, x0: float, y0: float, res: float) -> np.ndarray:
    """Closed solid: the heightfield on top, vertical side walls, flat bottom at z = 0.

    h[i, j] is the height at (x0 + j * res, y0 + i * res); row 0 is the south edge.
    """
    ny, nx = h.shape
    xs, ys = x0 + np.arange(nx) * res, y0 + np.arange(ny) * res
    gx, gy = np.meshgrid(xs, ys)
    top = np.stack([gx, gy, h], axis=-1)
    a, b, c, d = top[:-1, :-1], top[:-1, 1:], top[1:, 1:], top[1:, :-1]
    tris = [np.stack([a, b, c], -2).reshape(-1, 3, 3), np.stack([a, c, d], -2).reshape(-1, 3, 3)]
    ring = _perimeter(top)                                    # counter-clockwise seen from above
    p, q = ring, np.roll(ring, -1, axis=0)
    pb, qb = p * [1, 1, 0], q * [1, 1, 0]
    tris += [np.stack([pb, qb, q], 1), np.stack([pb, q, p], 1)]
    centre = np.broadcast_to([xs.mean(), ys.mean(), 0.0], pb.shape)
    tris.append(np.stack([centre, qb, pb], 1))
    return np.concatenate(tris)


def _perimeter(grid: np.ndarray) -> np.ndarray:
    south = grid[0, :-1]
    east = grid[:-1, -1]
    north = grid[-1, :0:-1]
    west = grid[:0:-1, 0]
    return np.concatenate([south, east, north, west])


def box(x_lo: float, y_lo: float, x_hi: float, y_hi: float, z_lo: float, z_hi: float) -> np.ndarray:
    h = np.full((2, 2), z_hi)
    solid = heightfield_solid(h, x_lo, y_lo, 1.0)
    # heightfield_solid builds a unit cell; stretch it to the box and lift the bottom
    solid[..., 0] = x_lo + (solid[..., 0] - x_lo) * (x_hi - x_lo)
    solid[..., 1] = y_lo + (solid[..., 1] - y_lo) * (y_hi - y_lo)
    solid[..., 2] = np.where(solid[..., 2] == 0.0, z_lo, solid[..., 2])
    return solid


def ribbon(line: np.ndarray, half_width: float, height_at, lift: float, sink: float) -> np.ndarray | None:
    """Closed strip along a polyline (k, 2) following the terrain: top at ground + lift, bottom at ground - sink."""
    if len(line) < 2:
        return None
    seg = np.diff(line, axis=0)
    tang = np.vstack([seg[:1], seg[:-1] + seg[1:], seg[-1:]])
    norm = np.linalg.norm(tang, axis=1, keepdims=True)
    if np.any(norm == 0):
        return None
    left = np.column_stack([-tang[:, 1], tang[:, 0]]) / norm * half_width
    lxy, rxy = line + left, line - left
    zl, zr = height_at(lxy[:, 0], lxy[:, 1]), height_at(rxy[:, 0], rxy[:, 1])
    if np.isnan(zl).any() or np.isnan(zr).any():
        return None
    lt, rt = np.column_stack([lxy, zl + lift]), np.column_stack([rxy, zr + lift])
    lb, rb = np.column_stack([lxy, zl - sink]), np.column_stack([rxy, zr - sink])
    # cross-section ring (counter-clockwise looking along the direction of travel): rt, lt, lb, rb
    ring = np.stack([rt, lt, lb, rb], axis=1)                     # (k, 4, 3)
    tris = []
    for s in range(4):
        a, b = ring[:-1, s], ring[:-1, (s + 1) % 4]
        c, d = ring[1:, (s + 1) % 4], ring[1:, s]
        tris += [np.stack([a, d, c], 1), np.stack([a, c, b], 1)]
    start, end = ring[0], ring[-1]
    tris += [np.stack([start[[0]], start[[1]], start[[2]]], 1), np.stack([start[[0]], start[[2]], start[[3]]], 1),
             np.stack([end[[0]], end[[2]], end[[1]]], 1), np.stack([end[[0]], end[[3]], end[[2]]], 1)]
    return np.concatenate(tris)


def is_watertight(tris: np.ndarray, decimals: int = 6) -> bool:
    """Every directed edge appears exactly once and is matched by its reverse (closed, consistently wound)."""
    v = np.round(tris, decimals)
    edges = Counter()
    for k in range(3):
        a, b = v[:, k], v[:, (k + 1) % 3]
        edges.update(zip(map(tuple, a), map(tuple, b)))
    return all(n == 1 and edges.get((e[1], e[0]), 0) == 1 for e, n in edges.items())


def write_stl(path: Path, tris: np.ndarray) -> None:
    tris = np.asarray(tris, dtype=np.float32)
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    rec = np.zeros(len(tris), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    rec["n"], rec["v"] = n, tris
    with path.open("wb") as fh:
        fh.write(STL_HEADER)
        fh.write(np.uint32(len(tris)).tobytes())
        fh.write(rec.tobytes())


def volume_mm3(tris: np.ndarray) -> float:
    """Signed volume by the divergence theorem (positive for an outward-wound closed mesh)."""
    t = np.asarray(tris, dtype=float)
    return float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0)


def read_stl(path: Path) -> np.ndarray:
    """Binary or ASCII STL -> (n, 3, 3) triangles."""
    data = path.read_bytes()
    if len(data) >= 84:
        n = int(np.frombuffer(data[80:84], dtype="<u4")[0])
        if 84 + 50 * n == len(data):
            rec = np.frombuffer(data[84:], dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")], count=n)
            return rec["v"].astype(float)
    verts = [list(map(float, ln.split()[1:4])) for ln in data.decode(errors="ignore").splitlines()
             if ln.strip().startswith("vertex")]
    if not verts or len(verts) % 3:
        raise ValueError(f"{path} is not a readable STL")
    return np.array(verts).reshape(-1, 3, 3)
