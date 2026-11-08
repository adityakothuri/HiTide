"""Tag-free pose: the tray's own rim and terrain replace the ArUco tags (for badly printed tags)."""

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from gauge import camera, model, rim, synth  # noqa: E402
from gauge.water import GaugeReader  # noqa: E402

CLICK_NOISE_PX = 4.0
POSES = [(55, 30, 360), (60, 210, 400), (45, 120, 340)]  # elevation, azimuth, distance (stand mode)


@pytest.fixture(scope="module")
def tray():
    return model.load_tray()


def _corners_mm(tray):
    w, d, z = tray.size_mm[0], tray.size_mm[1], tray.rim_top_mm
    return np.array([[0, 0, z], [w, 0, z], [w, d, z], [0, d, z]], float)


def _scene(tray, el, az, dist, level_ft=None, seed=0):
    cam = camera.tello_default()
    pose = synth.look_at_pose(tray, distance_mm=dist, elevation_deg=el, azimuth_deg=az)
    level = None if level_ft is None else model.level_mm(tray, level_ft)
    frame = synth.render(tray, cam, pose, level, noise=synth.Noise.modest(), draw_tags=False,
                         rng=np.random.default_rng(seed))
    return cam, pose, frame


def _clicks(tray, cam, pose, rng):
    px = camera.project(_corners_mm(tray), cam, pose)[0]
    return px + rng.uniform(-CLICK_NOISE_PX, CLICK_NOISE_PX, px.shape)


@pytest.mark.parametrize("el,az,dist", POSES)
def test_clicked_corners_recover_the_camera(tray, el, az, dist):
    cam, pose, frame = _scene(tray, el, az, dist)
    fit = rim.solve_rim_pose(frame, tray, camera.tello_default(), corners_px=_clicks(tray, cam, pose,
                                                                                    np.random.default_rng(1)))
    assert rim.rim_problem(fit) is None
    assert _image_error_px(tray, cam, pose, fit) < 3.0
    assert fit.source == "corners"


def _image_error_px(tray, cam, pose, fit):
    """Mean pixel distance between where tray points land with the fitted vs the true pose."""
    pts = rim._edge_points(tray)[::10]
    true_px = camera.project(pts, cam, pose)[0]
    fit_px = camera.project(pts, fit.cam, fit.fix.pose)[0]
    return float(np.linalg.norm(true_px - fit_px, axis=1).mean())


@pytest.mark.parametrize("el,az,dist", POSES[:2])
def test_no_tags_reads_the_level_from_clicked_corners(tray, el, az, dist):
    cam, pose, dry = _scene(tray, el, az, dist, seed=5)
    reader = GaugeReader(tray)
    assert reader.set_corners(_clicks(tray, cam, pose, np.random.default_rng(2))) == (True, "ok")
    assert reader.set_baseline(dry) == (True, "ok")
    for ft in (1.5, 3.5, 5.5):
        _, _, wet = _scene(tray, el, az, dist, level_ft=ft, seed=6 + int(ft))
        est = reader.read(wet)
        assert est.ft is not None and abs(est.ft - ft) <= 0.5, (ft, est.reason)
        assert est.pose_source == "corners" and est.tags_seen == 0


def test_automatic_outline_is_right_or_says_so(tray):
    """Without clicks the reader may be unsure, but it must never report a confidently wrong pose."""
    for el, az, dist in POSES:
        cam, pose, frame = _scene(tray, el, az, dist, seed=9)
        fit = rim.solve_rim_pose(frame, tray, camera.tello_default())
        if rim.rim_problem(fit) is None:
            assert _image_error_px(tray, cam, pose, fit) < 5.0
        else:
            assert "click the 4 tray corners" in rim.rim_problem(fit)


def test_tags_still_win_when_present(tray):
    cam = camera.tello_default()
    pose = synth.look_at_pose(tray, distance_mm=340, elevation_deg=55, azimuth_deg=30)
    frame = synth.render(tray, cam, pose, model.level_mm(tray, 2.5), noise=synth.Noise.modest())
    reader = GaugeReader(tray)
    reader.set_corners(_clicks(tray, cam, pose, np.random.default_rng(3)))
    assert reader.read(frame).pose_source == "tags"


def test_locked_pose_is_reused_while_camera_still_and_resolved_when_it_moves(tray, monkeypatch):
    cam, pose, dry = _scene(tray, 55, 30, 360, seed=12)
    reader = GaugeReader(tray)
    reader.set_corners(_clicks(tray, cam, pose, np.random.default_rng(4)))
    calls = []
    real = rim.solve_rim_pose

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr("gauge.water.solve_rim_pose", counting)
    assert reader.set_baseline(dry)[0]
    for ft in (1.5, 3.5):  # water changes the inside of the tray, not the background
        _, _, wet = _scene(tray, 55, 30, 360, level_ft=ft, seed=13 + int(ft))
        assert reader.read(wet).valid
    assert len(calls) == 1
    _, _, moved = _scene(tray, 55, 75, 360, level_ft=3.5, seed=20)  # camera swung 45 deg round the tray
    reader.read(moved)
    assert len(calls) == 2


def test_set_corners_validates_input(tray):
    reader = GaugeReader(tray)
    assert reader.set_corners([[1, 2], [3, 4]])[0] is False
    assert reader.set_corners([[1, 1]] * 4)[0] is False
    assert reader.set_corners([[0, 0], [10, 0], [10, 10], [0, 10]]) == (True, "ok")
    assert reader.corners_px == [[0, 0], [10, 0], [10, 10], [0, 10]]
    reader.clear_corners()
    assert reader.corners_px is None


def test_no_pose_holds_the_last_reading(tray):
    cam, pose, dry = _scene(tray, 55, 30, 360, seed=30)
    reader = GaugeReader(tray)
    reader.set_corners(_clicks(tray, cam, pose, np.random.default_rng(5)))
    reader.set_baseline(dry)
    _, _, wet = _scene(tray, 55, 30, 360, level_ft=3.5, seed=31)
    first = reader.update(wet)
    blank = np.zeros_like(wet)  # lens covered / hand over the camera
    held = reader.update(blank)
    assert first.valid and held.ft == first.ft
