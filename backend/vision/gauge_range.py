"""USGS gauge reading over a time window, for labelling real flood footage (drone vision demo).

The gauge is a separate source from the vision model: it reports stage (ft) on its own datum. Gauge
08166200 (Guadalupe Rv at Kerrville) has datum 1601.14 ft NAVD88 (USGS site file), the same vertical
datum as 3DEP lidar, so water-surface elevation = datum + stage, comparable with the model's NAVD88 WSE.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

M_PER_FT = 0.3048
KERRVILLE_SITE = "08166200"
KERRVILLE_DATUM_FT = 1601.14       # NAVD88, USGS site inventory (alt_datum_cd NAVD88)


def epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


@dataclass(frozen=True)
class GaugeSeries:
    site: str
    name: str
    datum_ft: float
    t: np.ndarray            # epoch seconds, ascending
    stage_ft: np.ndarray

    @staticmethod
    def load(path: Path, site: str = KERRVILLE_SITE, datum_ft: float = KERRVILLE_DATUM_FT) -> "GaugeSeries":
        g = json.loads(Path(path).read_text())["gauges"][site]
        pts = sorted((epoch(t), float(v)) for t, v in g["series"] if v is not None)
        t, s = np.array(pts).T
        return GaugeSeries(site, g.get("name", site), float(g.get("datum_ft") or datum_ft), t, s)

    def stage_at(self, t: float) -> float | None:
        if not (self.t[0] <= t <= self.t[-1]):
            return None
        return float(np.interp(t, self.t, self.stage_ft))

    def stage_range(self, t0: float, t1: float) -> tuple[float, float] | None:
        """Min/max stage over [t0, t1], including interpolated end points. None outside the record."""
        if t1 < t0:
            t0, t1 = t1, t0
        lo, hi = max(t0, self.t[0]), min(t1, self.t[-1])
        if lo > hi:
            return None
        inside = self.stage_ft[(self.t >= lo) & (self.t <= hi)]
        ends = [float(np.interp(lo, self.t, self.stage_ft)), float(np.interp(hi, self.t, self.stage_ft))]
        vals = np.concatenate([inside, ends])
        return float(vals.min()), float(vals.max())

    def wse_ft(self, stage_ft: float) -> float:
        return self.datum_ft + stage_ft

    def crossings(self, stage_ft: float) -> list[tuple[float, str]]:
        """Times the stage passed through a level, with direction ('rising'/'falling')."""
        s, t = self.stage_ft - stage_ft, self.t
        out = []
        for i in np.nonzero(np.sign(s[:-1]) * np.sign(s[1:]) < 0)[0]:
            f = s[i] / (s[i] - s[i + 1])
            out.append((float(t[i] + f * (t[i + 1] - t[i])), "rising" if s[i + 1] > s[i] else "falling"))
        return out
