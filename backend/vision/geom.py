"""Small 2-D polyline helpers shared by the pipeline and the synthetic renderer."""

from __future__ import annotations

import numpy as np


def densify(poly: np.ndarray, step: float) -> np.ndarray:
    """Points along a polyline every <= step metres, including both ends."""
    poly = np.asarray(poly, dtype=float)
    out = [poly[0]]
    for a, b in zip(poly[:-1], poly[1:]):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
        out.extend(a + (b - a) * (k / n) for k in range(1, n + 1))
    return np.array(out)


def dist_to_polyline(xy: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Shortest distance from each point (n, 2) to a polyline (k, 2)."""
    poly = np.asarray(poly, dtype=float)
    d = np.full(len(xy), np.inf)
    for a, b in zip(poly[:-1], poly[1:]):
        ab = b - a
        t = np.clip(((xy - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
        d = np.minimum(d, np.linalg.norm(xy - (a + t[:, None] * ab), axis=1))
    return d
