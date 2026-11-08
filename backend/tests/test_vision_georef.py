"""Georeferencing real footage: pose <-> rotation, rotation tracking, pose fit; and the gauge window."""

import math

import numpy as np
import pytest

from vision.camera import Intrinsics, Pose, project, rotation
from vision.gauge_range import GaugeSeries
from vision.georef import (
    Priors, fit_pose, k_matrix, pose_from_rotation, rotate_pose, rotation_from_homography,
)


@pytest.mark.parametrize("h,p,r", [(0, 10, 0), (183, 8, -2), (95, 45, 3), (270, 80, 1)])
def test_pose_rotation_round_trip(h, p, r):
    pose = Pose(1, 2, 3, h, p, r)
    back = pose_from_rotation(rotation(pose), 1, 2, 3)
    assert back.heading_deg == pytest.approx(h % 360, abs=1e-6)
    assert back.pitch_deg == pytest.approx(p, abs=1e-6) and back.roll_deg == pytest.approx(r, abs=1e-6)


def test_pure_rotation_homography_recovers_the_turn():
    cam = Intrinsics.from_hfov(1280, 720, 66)
    a = Pose(0, 0, 10, 180, 8, 0)
    b = Pose(0, 0, 10, 186, 9.5, 1.0)
    r_rel = rotation(b) @ rotation(a).T
    k = k_matrix(cam)
    h = k @ r_rel @ np.linalg.inv(k)
    got = rotate_pose(a, rotation_from_homography(h, cam))
    assert got.heading_deg == pytest.approx(186, abs=1e-6) and got.pitch_deg == pytest.approx(9.5, abs=1e-6)


def test_fit_pose_recovers_orientation_from_points_on_a_mapped_line():
    size = (1280, 720)
    truth_cam = Intrinsics.from_hfov(*size, 64.0)
    truth = Pose(1.5, -2.0, 101.6, 183.0, 9.0, 1.0)
    line = np.array([[-80.0, -12.0], [-40.0, -18.0], [0.0, -25.0], [40.0, -26.0], [80.0, -33.0]])
    xs = np.linspace(-30, 25, 9)
    pts = np.column_stack([xs, np.interp(xs, line[:, 0], line[:, 1]), np.full(9, 96.0)])
    uv, _ = project(truth_cam, truth, pts)
    fit = fit_pose(uv, line, 96.0, size, (0.0, 0.0), 100.0,
                   Priors(heading=(180, 20), pitch=(8, 5), hfov=(66, 6), eye_m=(1.5, 0.7)), px_sigma=1.0)
    assert fit.rms_m < 0.3
    assert abs((fit.pose.heading_deg - 183.0 + 180) % 360 - 180) < 3.0
    assert abs(fit.pose.pitch_deg - 9.0) < 1.5
    assert fit.sigma_deg > 0 and math.isfinite(fit.sigma_m)


def _series():
    t0 = 1_751_600_000.0
    t = t0 + np.arange(0, 5) * 900.0
    return GaugeSeries("x", "x", 1601.14, t, np.array([1.0, 10.0, 37.5, 30.0, 20.0])), t0


def test_stage_range_spans_the_window_including_interpolated_ends():
    g, t0 = _series()
    assert g.stage_range(t0 + 450, t0 + 1350) == (pytest.approx(5.5), pytest.approx(23.75))
    assert g.stage_range(t0 + 450, t0 + 2000) == (pytest.approx(5.5), pytest.approx(37.5))
    assert g.stage_range(t0 - 9e5, t0 - 8e5) is None
    assert g.wse_ft(37.5) == pytest.approx(1638.64)


def test_crossings_report_rising_and_falling_times():
    g, t0 = _series()
    c = g.crossings(25.0)
    assert [d for _, d in c] == ["rising", "falling"]
    assert t0 + 900 < c[0][0] < t0 + 1800 and t0 + 2700 < c[1][0] < t0 + 3600


def test_shoreline_pixels_take_the_lowest_water_pixel_above_open_ground():
    from vision.demo_video import shoreline_pixels
    from vision.grid import Seg
    from vision.segment import lut_from_names
    from vision.synth import ADE

    labels = np.full((120, 64), ADE["grass"], np.int16)
    labels[:40] = ADE["sky"]
    p = np.zeros((120, 64), np.float32)
    p[40:80] = 0.9                                   # water rows 40-79, grass below
    p[40:100, 30:40] = 0.9                           # a tongue of water reaching lower in a few columns
    labels[60:100, 50:60] = ADE["tree"]              # trees below the water: not a shoreline
    px = shoreline_pixels(Seg(labels, p), lut_from_names(), step=4)
    rows = dict(zip(px[:, 0].astype(int), px[:, 1]))
    assert rows[2] == 79.5 and rows[34] == 99.5
    assert all(not (50 <= u < 60) for u in rows)
