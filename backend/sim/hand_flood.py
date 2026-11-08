"""Replay flood on real terrain: HAND-style ("fill the low ground") depth from real gauge stage (overview.md 6.5).

Water surface at a river point s and time t:
    WSE(s, t) = z_ref(s) + rise(s, t)
  z_ref(s)   low-flow water surface from the DEM (lidar returns the water surface, not the bed)
  rise(s, t) stage above the pre-event base, interpolated between the bracketing gauges on that waterway,
             each read with the flood-wave travel-time lag (s - s_g) / c
Road depth = max(0, WSE at the road's nearest river point - road elevation).

Truth vs belief: the TRUTH replay fills a dead gauge's gap from a downstream gauge's shape (the water
didn't stop when the Hunt gauge died at 05:10 CDT). BELIEF uses only readings that exist, so an offline
gauge is unknown, which is exactly where drones add information. Not a hydraulic model (labelled in UI).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

import numpy as np

from sim.flood import M_TO_IN

FT_TO_M = 0.3048
MAX_GAP_S = 1800.0            # no reading within 30 min -> unknown
LOW_WATER_FREEBOARD_M = 0.6   # a low-water crossing deck sits just above normal flow
BRIDGE_FREEBOARD_M = 6.0      # a minor-stream bridge needs a big rise to overtop


@dataclass(frozen=True)
class Gauge:
    site: str
    s_m: float                # chainage on its waterway (0 = upstream end)
    times: np.ndarray         # epoch seconds, ascending
    stage_ft: np.ndarray
    base_ft: float            # pre-event stage
    max_gap_s: float = MAX_GAP_S   # no reading within this -> unknown (live telemetry lags, so it can be longer)

    def reported_rise_m(self, t: float) -> float | None:
        """Belief: the last reading at or before t (no interpolation toward a reading that doesn't exist yet)."""
        k = int(np.searchsorted(self.times, t, side="right")) - 1
        if k < 0 or t - self.times[k] > self.max_gap_s:
            return None
        return max(0.0, float(self.stage_ft[k]) - self.base_ft) * FT_TO_M

    def rise_m(self, t: float) -> float | None:
        if self.times.size == 0 or t < self.times[0] - self.max_gap_s or t > self.times[-1] + self.max_gap_s:
            return None
        i = int(np.searchsorted(self.times, t))
        neighbours = [self.times[j] for j in (i - 1, i) if 0 <= j < self.times.size]
        if min(abs(t - n) for n in neighbours) > self.max_gap_s:
            return None
        stage = float(np.interp(t, self.times, self.stage_ft))
        return max(0.0, stage - self.base_ft) * FT_TO_M

    def reported_rise_m_vec(self, ts: np.ndarray) -> np.ndarray:
        ts = np.asarray(ts, dtype=float)
        if self.times.size == 0:
            return np.full(ts.shape, np.nan)
        k = np.searchsorted(self.times, ts, side="right") - 1
        ok = (k >= 0) & (ts - self.times[np.clip(k, 0, None)] <= self.max_gap_s)
        rise = np.maximum(0.0, self.stage_ft[np.clip(k, 0, None)] - self.base_ft) * FT_TO_M
        return np.where(ok, rise, np.nan)

    def rise_m_vec(self, ts: np.ndarray) -> np.ndarray:
        """Vector form of rise_m: NaN where there is no reading within MAX_GAP_S."""
        ts = np.asarray(ts, dtype=float)
        if self.times.size == 0:
            return np.full(ts.shape, np.nan)
        i = np.clip(np.searchsorted(self.times, ts), 1, self.times.size - 1)
        gap = np.minimum(np.abs(ts - self.times[i - 1]), np.abs(ts - self.times[i]))
        if self.times.size == 1:
            gap = np.abs(ts - self.times[0])
        stage = np.interp(ts, self.times, self.stage_ft)
        rise = np.maximum(0.0, stage - self.base_ft) * FT_TO_M
        return np.where(gap <= self.max_gap_s, rise, np.nan)


def interp_rise_m(gauges: Sequence[Gauge], s: float, t: float, celerity_mps: float,
                  causal: bool = False) -> float | None:
    """Rise above base at chainage s: blend the two bracketing reporting gauges, each read with travel lag.
    causal=True (belief): never read a gauge later than now, and only values it has actually reported."""
    readings = []
    for g in gauges:
        read_t = t - (s - g.s_m) / celerity_mps
        r = g.reported_rise_m(min(read_t, t)) if causal else g.rise_m(read_t)
        if r is not None:
            readings.append((g.s_m, r))
    if not readings:
        return None
    readings.sort()
    above = [(sg, r) for sg, r in readings if sg <= s]
    below = [(sg, r) for sg, r in readings if sg > s]
    if above and below:
        (s1, r1), (s2, r2) = above[-1], below[0]
        w = (s - s1) / (s2 - s1)
        return (1 - w) * r1 + w * r2
    return (above[-1] if above else below[0])[1]


def interp_rise_vec(gauges: Sequence[Gauge], s: np.ndarray, t: float, celerity_mps: float,
                    causal: bool = False) -> np.ndarray:
    """Vector form of interp_rise_m over many chainages; NaN where no gauge reports."""
    s = np.asarray(s, dtype=float)
    ordered = sorted(gauges, key=lambda g: g.s_m)
    if not ordered:
        return np.full(s.shape, np.nan)
    gs = np.array([g.s_m for g in ordered])
    def read(g: Gauge) -> np.ndarray:
        read_t = t - (s - g.s_m) / celerity_mps
        return g.reported_rise_m_vec(np.minimum(read_t, t)) if causal else g.rise_m_vec(read_t)
    reads = np.vstack([read(g) for g in ordered])  # (G, N)
    out = np.full(s.shape, np.nan)
    for n in range(s.size):
        ok = ~np.isnan(reads[:, n])
        if not ok.any():
            continue
        sg, r = gs[ok], reads[ok, n]
        above, below = np.nonzero(sg <= s[n])[0], np.nonzero(sg > s[n])[0]
        if above.size and below.size:
            a, b = above[-1], below[0]
            w = (s[n] - sg[a]) / (sg[b] - sg[a])
            out[n] = (1 - w) * r[a] + w * r[b]
        else:
            out[n] = r[above[-1]] if above.size else r[below[0]]
    return out


def fill_gap(dead: Gauge, donor: Gauge, lag_s: float, until_s: float, step_s: float = 900.0) -> Gauge:
    """Truth only: bridge every outage of a dead gauge with the donor's shape (read `lag_s` later), scaled to
    match the last reading before each outage. An outage is a gap > max(30 min, 3x normal spacing), or the
    end of the series up to `until_s`. Real readings are never changed."""
    spacing = np.diff(dead.times)
    outage_s = max(MAX_GAP_S, 3 * float(np.median(spacing))) if spacing.size else MAX_GAP_S
    spans = [(float(dead.times[k]), float(dead.times[k + 1])) for k in np.flatnonzero(spacing > outage_s)]
    if dead.times.size and dead.times[-1] < until_s:
        spans.append((float(dead.times[-1]), until_s + step_s))
    extra_t, extra_stage = [], []
    for last_t, resume_t in spans:
        last_rise = dead.rise_m(last_t) or 0.0
        donor_at_fail = donor.rise_m(last_t + lag_s) or 0.0
        scale = last_rise / donor_at_fail if donor_at_fail > 0 else 1.0
        for t in np.arange(last_t + step_s, min(resume_t, until_s + step_s), step_s):
            r = donor.rise_m(float(t) + lag_s)
            if r is not None:
                extra_t.append(float(t))
                extra_stage.append(dead.base_ft + r * scale / FT_TO_M)
    times = np.concatenate([dead.times, extra_t])
    order = np.argsort(times, kind="stable")
    return replace(dead, times=times[order], stage_ft=np.concatenate([dead.stage_ft, extra_stage])[order])


def road_depth_in(ref_z_m: float, rise_m: float | None, road_z_m: float) -> float:
    if rise_m is None:
        return 0.0
    return max(0.0, ref_z_m + rise_m - road_z_m) * M_TO_IN


def crossing_depth_in(rise_m: float | None, bridge: bool) -> float:
    """A road over an unnamed stream: water over the deck once the rise beats the deck's freeboard."""
    if rise_m is None:
        return 0.0
    freeboard = BRIDGE_FREEBOARD_M if bridge else LOW_WATER_FREEBOARD_M
    return max(0.0, rise_m - freeboard) * M_TO_IN
