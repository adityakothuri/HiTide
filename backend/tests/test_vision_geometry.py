"""Camera model, ground grid labelling and voting (drone vision plan 5.3, plan fixes #1 and #2)."""

import numpy as np
import pytest

from vision.camera import Intrinsics, Pose, project, ray_to_plane, rays
from vision.grid import GROUND, INVALID, WATER, CellObs, GroundGrid, label_cells, visible, vote
from vision.segment import lut_from_names
from vision.synth import ADE, default_camera, make_frame, oblique_pose, render, valley_scene

CAM = Intrinsics.from_hfov(640, 480, 80.0)
LUT = lut_from_names()


def test_nadir_camera_image_top_is_north_and_right_is_east():
    pose = Pose(0, 0, 100, heading_deg=0, pitch_deg=90)
    uv, depth = project(CAM, pose, np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]]))
    assert depth[0] == pytest.approx(100)
    assert uv[0] == pytest.approx([320, 240])
    assert uv[1][0] > 320 and uv[1][1] == pytest.approx(240)   # east -> right
    assert uv[2][1] < 240 and uv[2][0] == pytest.approx(320)   # north -> up


@pytest.mark.parametrize("heading,pitch,roll", [(0, 90, 0), (37, 50, 0), (210, 35, 4), (300, 65, -3)])
def test_project_then_ray_to_plane_round_trips(heading, pitch, roll):
    pose = Pose(3, -8, 120, heading, pitch, roll)
    pts = np.array([[5.0, 60.0, 2.0], [-20.0, 40.0, 2.0], [30.0, 90.0, 2.0]])
    # put the points in front of the camera along its heading
    rad = np.radians(heading)
    shift = np.array([np.sin(rad), np.cos(rad), 0.0]) * 50 if pitch < 89 else np.zeros(3)
    pts = pts - np.array([0, 60, 0]) + shift
    uv, depth = project(CAM, pose, pts)
    assert (depth > 0).all()
    back = ray_to_plane(CAM, pose, uv, 2.0)
    assert np.allclose(back, pts, atol=1e-6)


def test_rays_are_unit_and_point_down_for_nadir():
    d = rays(CAM, Pose(0, 0, 50, 0, 90), np.array([[320, 240], [0, 0]]))
    assert np.allclose(np.linalg.norm(d, axis=1), 1)
    assert (d[:, 2] < 0).all()


def test_ray_to_plane_returns_nan_for_rays_above_the_horizon():
    p = ray_to_plane(CAM, Pose(0, 0, 50, 0, 0), np.array([[320, 10]]), 0.0)
    assert np.isnan(p).all()


def test_height_at_is_bilinear_and_nan_outside():
    g = GroundGrid(0, 0, 1.0, np.array([[0.0, 1.0], [2.0, 3.0]]))
    assert g.height_at(np.array([0.5]), np.array([0.5]))[0] == pytest.approx(1.5)
    assert np.isnan(g.height_at(np.array([5.0]), np.array([0.5]))[0])


def test_cells_behind_a_ridge_are_not_visible():
    x = np.arange(0, 41) * 1.0
    z = np.where((x >= 18) & (x <= 20), 30.0, 0.0)[None, :].repeat(3, axis=0)
    g = GroundGrid(0, -1, 1.0, z)
    pose = Pose(-10, 0, 10, heading_deg=90, pitch_deg=10)   # low, looking east across the ridge
    pts = np.array([[10.0, 0.0, 0.0], [35.0, 0.0, 0.0]])
    assert visible(g, pose, pts, steps=64).tolist() == [True, False]


def test_label_cells_matches_the_independent_renderer():
    scene = valley_scene()
    cam = default_camera()
    pose = oblique_pose(scene)
    frame = make_frame(scene, cam, pose, rendered=render(scene, cam, pose))
    obs = label_cells(scene.grid, frame.seg, cam, pose, LUT)
    seen = obs.group != INVALID
    assert seen.mean() > 0.3
    truth_wet = scene.grid.z < scene.wse_m
    wet = obs.group == WATER
    # agreement away from the exact boundary (renderer and projector disagree only within ~1 cell there)
    interior = seen & (np.abs(scene.grid.z - scene.wse_m) > 0.15)
    assert (wet[interior] == truth_wet[interior]).mean() > 0.99


def test_vote_takes_majority_per_cell_and_ignores_unseen_frames():
    w, gr, inv = WATER, GROUND, INVALID
    obs = [
        CellObs(np.array([[w, gr]], dtype=np.int8), np.array([[0.9, 0.1]])),
        CellObs(np.array([[w, inv]], dtype=np.int8), np.array([[0.8, np.nan]])),
        CellObs(np.array([[gr, inv]], dtype=np.int8), np.array([[0.2, np.nan]])),
    ]
    out = vote(obs)
    assert out.group.tolist() == [[WATER, GROUND]]
    assert out.p_water[0, 0] >= 0.5 and out.p_water[0, 1] < 0.5


def test_vote_of_all_unseen_cell_stays_invalid():
    obs = [CellObs(np.array([[INVALID]], dtype=np.int8), np.array([[np.nan]]))] * 3
    out = vote(obs)
    assert out.group[0, 0] == INVALID and np.isnan(out.p_water[0, 0])


def test_renderer_ade_ids_are_consistent():
    assert LUT[ADE["water"]] == WATER and LUT[ADE["road"]] == GROUND and LUT[ADE["grass"]] == GROUND


def test_oblique_projection_matches_hand_computed_pinhole_values():
    """Independent of camera.rotation(): expected pixels worked out by hand, so a convention bug in the
    shared camera code can't cancel between the synthetic renderer and the estimator.

    Camera 100 m up, facing north (heading 0), tilted 45 deg below the horizon, f = 500 px, 640x480.
    Ground point straight ahead along the optical axis: (0, 100, 0) -> principal point (320, 240), depth 100*sqrt2.
    Ground point (10, 100, 0): camera-right offset 10 m at the same depth -> u = 320 + 500*10/(100*sqrt2).
    Ground point (0, 200, 0): forward f = 200*cos45 + 100*sin45 = 300/sqrt2, down d = -200*sin45 + 100*cos45
    = -100/sqrt2 (above the axis) -> v = 240 + 500*(-100)/300 = 73.33.
    """
    cam = Intrinsics(500.0, 500.0, 320.0, 240.0, 640, 480)
    pose = Pose(0.0, 0.0, 100.0, heading_deg=0.0, pitch_deg=45.0)
    pts = np.array([[0.0, 100.0, 0.0], [10.0, 100.0, 0.0], [0.0, 200.0, 0.0]])
    uv, depth = project(cam, pose, pts)
    s2 = np.sqrt(2.0)
    np.testing.assert_allclose(uv[0], [320.0, 240.0], atol=1e-6)
    np.testing.assert_allclose(depth[0], 100 * s2, rtol=1e-9)
    np.testing.assert_allclose(uv[1], [320.0 + 500 * 10 / (100 * s2), 240.0], atol=1e-6)
    np.testing.assert_allclose(uv[2], [320.0, 240.0 - 500 * 100 / 300], atol=1e-6)
    # heading 90 (facing east): the same geometry rotated, point ahead is (100, 0, 0)
    east = Pose(0.0, 0.0, 100.0, heading_deg=90.0, pitch_deg=45.0)
    uv_e, _ = project(cam, east, np.array([[100.0, 0.0, 0.0], [100.0, -10.0, 0.0]]))
    np.testing.assert_allclose(uv_e[0], [320.0, 240.0], atol=1e-6)
    np.testing.assert_allclose(uv_e[1], [320.0 + 500 * 10 / (100 * s2), 240.0], atol=1e-6)  # south is right
