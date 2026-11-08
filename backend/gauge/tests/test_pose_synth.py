import time

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from gauge.camera import camera_position_mm, project, tello_default  # noqa: E402
from gauge.model import level_mm, load_tray  # noqa: E402
from gauge.pose import detect_tags, estimate_focal, solve_pose  # noqa: E402
from gauge.synth import Noise, look_at_pose, render  # noqa: E402

CAM = tello_default()
GRID = [(400, 45, 0), (400, 50, 90), (400, 55, 180), (400, 65, 270), (320, 40, 45), (450, 50, 135)]


@pytest.fixture(scope="module")
def model():
    return load_tray()


def test_look_at_pose_points_at_target(model):
    pose = look_at_pose(model, 400, 45, 30)
    assert np.linalg.norm(camera_position_mm(pose) - np.array([80, 80, 10.0])) == pytest.approx(400)
    px, depth = project(np.array([[80.0, 80.0, 10.0]]), CAM, pose)
    assert np.allclose(px[0], [480, 360], atol=1e-6) and depth[0] == pytest.approx(400)


@pytest.mark.parametrize("dist,elev,azim", GRID)
def test_pose_recovery_on_renders(model, dist, elev, azim):
    pose = look_at_pose(model, dist, elev, azim)
    frame = render(model, CAM, pose, level_mm(model, 3.5), noise=Noise.modest(), rng=np.random.default_rng(1))
    fix = solve_pose(detect_tags(frame), model, CAM)
    assert fix is not None and len(fix.tag_ids) >= 3
    assert np.linalg.norm(fix.camera_mm - camera_position_mm(pose)) < 10.0
    assert fix.reproj_err_px < 3.0


def test_pose_tolerates_tags_raised_above_the_pad(model):
    pose = look_at_pose(model, 400, 45, 30)
    frame = render(model, CAM, pose, None, tag_z_offset_mm=0.4, noise=Noise.modest(),
                   rng=np.random.default_rng(2))
    fix = solve_pose(detect_tags(frame), model, CAM)
    assert fix is not None
    assert np.linalg.norm(fix.camera_mm - camera_position_mm(pose)) < 10.0


def test_none_when_fewer_than_three_tags(model):
    pose = look_at_pose(model, 400, 45, 30)
    frame = render(model, CAM, pose, None)
    seen = detect_tags(frame)
    assert solve_pose(seen, model, CAM) is not None
    for keep in (2, 1, 0):
        assert solve_pose(dict(list(seen.items())[:keep]), model, CAM) is None
    masked = frame.copy()
    for corners in list(seen.values())[:2]:  # white-out two tags
        x0, y0 = corners.min(axis=0).astype(int) - 4
        x1, y1 = corners.max(axis=0).astype(int) + 4
        masked[y0:y1, x0:x1] = 255
    assert solve_pose(detect_tags(masked), model, CAM) is None


def test_detect_tags_handles_empty_input():
    assert detect_tags(np.zeros((0, 0, 3), np.uint8)) == {}
    assert detect_tags(np.full((100, 100, 3), 128, np.uint8)) == {}


def test_estimate_focal_recovers_683_and_rejects_fronto_parallel(model):
    for dist, elev, azim in GRID[:4]:
        pose = look_at_pose(model, dist, elev, azim)
        seen = {i: project(c, CAM, pose)[0] for i, c in model.tag_corners_mm.items()}
        assert estimate_focal(seen, model, 960, 720) == pytest.approx(CAM.fx, rel=0.01)
    top_down = look_at_pose(model, 400, 89.9, 0)
    seen = {i: project(c, CAM, top_down)[0] for i, c in model.tag_corners_mm.items()}
    assert estimate_focal(seen, model, 960, 720) is None
    assert estimate_focal({0: seen[0]}, model, 960, 720) is None


def test_render_speed_and_determinism(model):
    pose = look_at_pose(model, 400, 45, 30)
    start = time.perf_counter()
    a = render(model, CAM, pose, level_mm(model, 2.5), rng=np.random.default_rng(5))
    assert time.perf_counter() - start < 2.5
    b = render(model, CAM, pose, level_mm(model, 2.5), rng=np.random.default_rng(5))
    assert a.shape == (720, 960, 3) and np.array_equal(a, b)


def test_render_water_is_blue_and_dry_is_not(model):
    pose = look_at_pose(model, 400, 50, 0)
    wet = render(model, CAM, pose, level_mm(model, 6.0)).astype(float)
    dry = render(model, CAM, pose, None).astype(float)
    assert (wet[..., 0] - wet[..., 2]).mean() > (dry[..., 0] - dry[..., 2]).mean() + 5
