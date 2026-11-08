from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from gauge.camera import (Intrinsics, Pose, camera_position_mm, load_intrinsics, project,  # noqa: E402
                          tello_default)
from gauge.model import level_ft, level_mm, load_tray  # noqa: E402
from gauge.synth import look_at_pose  # noqa: E402


@pytest.fixture(scope="module")
def model():
    return load_tray()


def test_load_default_tray(model):
    assert model.res_mm == pytest.approx(0.32)
    assert model.height_mm.shape == (501, 501)
    assert model.size_mm[0] == pytest.approx(160.0)
    assert sorted(model.tag_corners_mm) == [0, 1, 2, 3]
    assert model.tag_corners_mm[0].shape == (4, 3)
    assert model.tag_dictionary == "DICT_4X4_50"
    assert model.road.deck_mm == pytest.approx(4.6)
    assert model.car["roof_mm"] == pytest.approx(10.38)
    assert len(model.houses) == 10 and len(model.levels) == 8


def test_load_200mm_tray():
    root = Path(__file__).resolve().parents[3] / "data" / "gauge_tray"
    big = load_tray(root)
    assert big.res_mm == pytest.approx(0.4) and big.size_mm[0] == pytest.approx(200.0)


def test_load_tray_errors(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_tray(tmp_path)
    (tmp_path / "manifest.json").write_text("{}")
    np.savez(tmp_path / "truth.npz", height_mm=np.zeros((3, 3)), river=np.zeros((3, 3), bool))
    with pytest.raises(ValueError):
        load_tray(tmp_path)


def test_model_is_read_only(model):
    with pytest.raises(ValueError):
        model.height_mm[0, 0] = 5.0


def test_ft_mm_mapping(model):
    assert level_ft(model, 4.0) == 0.0
    assert level_ft(model, 18.0) == pytest.approx(7.0)
    assert level_mm(model, 3) == pytest.approx(10.0)
    for ft in (0, 1.5, 6.25):
        assert level_ft(model, level_mm(model, ft)) == pytest.approx(ft)


def test_tello_default_uses_diagonal_fov():
    cam = tello_default()
    assert cam.fx == pytest.approx(683, abs=1.5) and cam.fx == cam.fy
    assert (cam.cx, cam.cy) == (480, 360)


def test_load_intrinsics_default_and_file(tmp_path, monkeypatch):
    monkeypatch.delenv("GAUGE_CAMERA_JSON", raising=False)
    assert load_intrinsics(tmp_path / "missing.json").fx == pytest.approx(tello_default().fx)
    path = tmp_path / "cam.json"
    path.write_text('{"fx": 700, "cx": 470, "cy": 350}')
    cam = load_intrinsics(path)
    assert (cam.fx, cam.fy, cam.cx) == (700, 700, 470)
    path.write_text("not json")
    assert load_intrinsics(path).fx == pytest.approx(tello_default().fx)


def test_projection_round_trip_matches_opencv(model):
    cam = Intrinsics(683, 683, 480, 360)
    pose = look_at_pose(model, 400, 45, 30)
    pts = np.array([[10.0, 10.0, 21.6], [80.0, 80.0, 5.0], [150.0, 30.0, 12.0]])
    px, depth = project(pts, cam, pose)
    ref = cv2.projectPoints(pts, pose.rvec.reshape(3, 1), pose.tvec.reshape(3, 1), cam.matrix,
                            None)[0].reshape(-1, 2)
    assert np.allclose(px, ref, atol=1e-6)
    assert np.all(depth > 0)
    centre = camera_position_mm(pose)
    for p, uv in zip(pts, px):
        ray_cam = np.array([(uv[0] - cam.cx) / cam.fx, (uv[1] - cam.cy) / cam.fy, 1.0])
        ray = pose.rotation.T @ ray_cam
        hit = centre + (p[2] - centre[2]) / ray[2] * ray
        assert np.allclose(hit, p, atol=1e-6)


def test_points_behind_camera_are_nan():
    pose = Pose(np.zeros(3), np.array([0.0, 0.0, -10.0]))
    px, depth = project(np.array([[0.0, 0.0, 0.0]]), Intrinsics(500, 500, 100, 100), pose)
    assert np.isnan(px).all() and depth[0] < 0
