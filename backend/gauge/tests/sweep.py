"""Synthetic accuracy sweep shared by the tests and the accuracy report (not a test module)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from gauge.camera import tello_default
from gauge.model import TrayModel, level_mm
from gauge.synth import Noise, look_at_pose, render
from gauge.water import GaugeReader

# (distance mm, elevation deg, azimuth deg)
STAND_POSES = [(300, 35, 0), (350, 45, 60), (400, 55, 130), (450, 65, 200), (380, 40, 270), (330, 60, 320)]
HOVER_POSES = [(350, 22, 45), (400, 25, 160), (450, 20, 250)]
MID_STEP_FT = [k + 0.5 for k in range(7)]
EXACT_FT = [float(k) for k in range(8)]
HOVER_FT = [0.5, 2.5, 4.5, 6.5]
NOISE = Noise(blur_px=0.8, gauss_sigma=2.5, jpeg_quality=75, glare_blobs=1, pose_jitter_deg=0.0)


@dataclass(frozen=True)
class Case:
    mode: str
    baseline: bool
    ft_true: float
    ft_est: float | None
    confidence: float

    @property
    def error(self) -> float | None:
        return None if self.ft_est is None else abs(self.ft_est - self.ft_true)


def run_sweep(model: TrayModel, mode: str, poses: list[tuple[int, int, int]], levels: list[float],
              seed: int = 7) -> list[Case]:
    cam = tello_default()
    rng = np.random.default_rng(seed)
    cases: list[Case] = []
    for dist, elev, azim in poses:
        pose = look_at_pose(model, dist, elev, azim)
        dry = render(model, cam, pose, None, noise=NOISE, rng=rng)
        with_base, without = GaugeReader(model, cam), GaugeReader(model, cam)
        with_base.set_baseline(dry)
        for ft in levels:
            gain = float(rng.uniform(0.93, 1.07))
            noise = Noise(NOISE.blur_px, NOISE.gauss_sigma, NOISE.jpeg_quality, gain, NOISE.glare_blobs)
            frame = render(model, cam, pose, level_mm(model, ft), noise=noise, rng=rng)
            for reader, flag in ((with_base, True), (without, False)):
                est = reader.read(frame)
                cases.append(Case(mode, flag, ft, est.ft, est.confidence))
    return cases


def rate(cases: list[Case], tol: float, baseline: bool | None = None) -> float:
    pool = [c for c in cases if baseline is None or c.baseline == baseline]
    hits = [c for c in pool if c.error is not None and c.error <= tol + 1e-9]
    return len(hits) / max(1, len(pool))


def none_rate(cases: list[Case], baseline: bool) -> float:
    pool = [c for c in cases if c.baseline == baseline]
    return sum(c.ft_est is None for c in pool) / max(1, len(pool))
