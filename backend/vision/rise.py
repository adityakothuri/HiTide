"""Rise rate per critical point from repeated water-surface estimates (drone vision plan 6.3).

Two error structures, handled separately:
- Inside ONE hover the pose bias is shared by every frame, so it cancels out of a slope; frames are thinned
  to one median per block (they're correlated) and fitted with Theil-Sen + its 95% interval.
- ACROSS hovers (revisits) each hover has its own GPS/attitude bias, so hover medians are fitted with
  weighted least squares using each hover's systematic sigma. Ignoring this reads a 10 cm hover-to-hover
  offset over 10 min as ~24 in/hr.
A new hover starts on a time gap OR a new `visit` id: the pipeline bumps the visit when the reported pose
moves or drifts beyond a threshold, because that is when the GPS/attitude bias changes (a revisit 45 s later
with a fresh 10 cm bias otherwise reads as ~200 in/hr).
Trend is 'rising'/'falling' only when the 95% interval clears the threshold; otherwise 'steady' (interval
inside the steady band) or 'unknown' (no rate reported, never a noise number). Revisits extend the series.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Literal, Mapping

import numpy as np
from scipy.stats import theilslopes

M_TO_IN = 1 / 0.0254
IN_PER_HR = M_TO_IN * 3600.0
Z95 = 1.96
MAX_RATE_IN_PER_HR = 2000.0   # snapshot bound; anything beyond is a bad fit, not a flood
TrendName = Literal["rising", "falling", "steady", "unknown"]


@dataclass(frozen=True)
class Trend:
    trend: TrendName
    rate_in_per_hr: float | None
    lo_in_per_hr: float | None
    hi_in_per_hr: float | None
    n_blocks: int

    @property
    def rising(self) -> bool | None:
        return {"rising": True, "falling": False, "steady": False}.get(self.trend)


@dataclass(frozen=True)
class RiseTracker:
    """series[point] = ((t, wse_m, sigma_m, visit), ...); sigma_m is that estimate's systematic 1-sigma."""
    series: Mapping[str, tuple[tuple[float, float, float, int], ...]] = field(
        default_factory=lambda: MappingProxyType({}))
    block_s: float = 3.0
    min_points: int = 4
    hover_gap_s: float = 60.0
    threshold_in_per_hr: float = 0.5
    steady_band_in_per_hr: float = 3.0
    max_age_s: float = 3 * 3600.0

    def add(self, point_id: str, t: float, wse_m: float, sigma_m: float = 0.0, visit: int = 0) -> "RiseTracker":
        if not (np.isfinite(t) and np.isfinite(wse_m) and np.isfinite(sigma_m)):
            return self                       # a NaN would poison every later fit
        kept = tuple(p for p in self.series.get(point_id, ()) if t - p[0] <= self.max_age_s)
        series = MappingProxyType({**self.series, point_id: kept + ((t, wse_m, sigma_m, int(visit)),)})
        return replace(self, series=series)

    def _hovers(self, point_id: str) -> list[np.ndarray]:
        pts = np.array(self.series.get(point_id, ()), dtype=float).reshape(-1, 4)
        if len(pts) == 0:
            return []
        new = (np.diff(pts[:, 0]) > self.hover_gap_s) | (np.diff(pts[:, 3]) != 0)
        return np.split(pts[:, :3], np.nonzero(new)[0] + 1)

    def _blocks(self, hover: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        key = np.floor((hover[:, 0] - hover[0, 0]) / self.block_s)
        ts = np.array([np.median(hover[key == k, 0]) for k in np.unique(key)])
        zs = np.array([np.median(hover[key == k, 1]) for k in np.unique(key)])
        return ts, zs

    def _classify(self, rate: float, lo: float, hi: float, n: int) -> Trend:
        rate, lo, hi = float(rate), float(lo), float(hi)
        if not (np.isfinite(rate) and np.isfinite(lo) and np.isfinite(hi)) or abs(rate) > MAX_RATE_IN_PER_HR:
            return Trend("unknown", None, None, None, n)
        thr = self.threshold_in_per_hr
        if lo > thr:
            name: TrendName = "rising"
        elif hi < -thr:
            name = "falling"
        elif -self.steady_band_in_per_hr <= lo and hi <= self.steady_band_in_per_hr:
            name = "steady"
        else:
            return Trend("unknown", None, round(lo, 1), round(hi, 1), n)
        return Trend(name, round(rate, 1), round(lo, 1), round(hi, 1), n)

    def trend(self, point_id: str) -> Trend:
        hovers = self._hovers(point_id)
        if len(hovers) >= 2:
            return self._across_hovers(hovers)
        if not hovers:
            return Trend("unknown", None, None, None, 0)
        t, z = self._blocks(hovers[0])
        if len(t) < self.min_points or np.ptp(t) <= 0:
            return Trend("unknown", None, None, None, len(t))
        slope, _, lo, hi = theilslopes(z, t, alpha=0.95)
        return self._classify(slope * IN_PER_HR, lo * IN_PER_HR, hi * IN_PER_HR, len(t))

    def _across_hovers(self, hovers: list[np.ndarray]) -> Trend:
        t = np.array([np.median(h[:, 0]) for h in hovers])
        z = np.array([np.median(h[:, 1]) for h in hovers])
        # a hover's error: its systematic sigma, floored by its own scatter / sqrt(n) and 1 cm
        sig = np.array([max(float(np.median(h[:, 2])), float(np.std(h[:, 1])) / np.sqrt(len(h)), 0.01)
                        for h in hovers])
        w = 1.0 / sig**2
        tm = np.sum(w * t) / np.sum(w)
        sxx = np.sum(w * (t - tm) ** 2)
        if sxx <= 0:
            return Trend("unknown", None, None, None, len(hovers))
        slope = np.sum(w * (t - tm) * (z - np.sum(w * z) / np.sum(w))) / sxx
        se = np.sqrt(1.0 / sxx)
        rate, half = slope * IN_PER_HR, Z95 * se * IN_PER_HR
        return self._classify(rate, rate - half, rate + half, len(hovers))
