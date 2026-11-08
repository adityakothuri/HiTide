"""Tabletop model: fiducial pose, model<->world conversion, synthetic end-to-end on the built print model."""

import cv2
import numpy as np
import pytest

from vision.camera import Intrinsics, Pose, project, rotation
from vision.fiducials import detect_tags, pose_from_rotation, solve_pose

CAM = Intrinsics.from_hfov(960, 720, 82.6)
SIDE = 0.236                               # tray width in metres on the table
TAG = 0.020


def _tags(z: float = 0.026) -> dict[int, np.ndarray]:
    """Four 20 mm tags at the tray corners; corners TL, TR, BR, BL with the tag top facing north."""
    out = {}
    for tid, (cx, cy) in enumerate([(0.012, 0.012), (SIDE - 0.012, 0.012), (SIDE - 0.012, SIDE - 0.012), (0.012, SIDE - 0.012)]):
        t = TAG / 2
        out[tid] = np.array([[cx - t, cy + t, z], [cx + t, cy + t, z], [cx + t, cy - t, z], [cx - t, cy - t, z]])
    return out


POSES = [
    Pose(0.118, 0.118, 0.40, 0.0, 90.0),
    Pose(0.118, -0.10, 0.33, 0.0, 55.0),
    Pose(0.30, 0.05, 0.30, 290.0, 60.0, 2.0),
]


@pytest.mark.parametrize("pose", POSES)
def test_pose_round_trips_through_rotation_matrix(pose):
    back = pose_from_rotation(rotation(pose), np.array([pose.x, pose.y, pose.z]))
    assert np.allclose(rotation(back), rotation(pose), atol=1e-9)
    assert (back.x, back.y, back.z) == pytest.approx((pose.x, pose.y, pose.z))


@pytest.mark.parametrize("pose", POSES)
def test_solve_pose_recovers_camera_from_projected_tag_corners(pose):
    tags = _tags()
    seen = {tid: project(CAM, pose, c)[0] for tid, c in tags.items()}
    est = solve_pose(seen, tags, CAM)
    assert est is not None
    assert np.linalg.norm([est.x - pose.x, est.y - pose.y, est.z - pose.z]) < 1e-4
    assert np.allclose(rotation(est), rotation(pose), atol=1e-4)


def test_solve_pose_needs_a_tag():
    assert solve_pose({}, _tags(), CAM) is None


def _draw_tags(pose: Pose) -> np.ndarray:
    img = np.full((CAM.height, CAM.width, 3), 140, np.uint8)
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    for tid, corners in _tags().items():
        px = 200
        marker = cv2.cvtColor(cv2.aruco.generateImageMarker(d, tid, px), cv2.COLOR_GRAY2BGR)
        marker = cv2.copyMakeBorder(marker, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        src = np.float32([[40, 40], [40 + px, 40], [40 + px, 40 + px], [40, 40 + px]])
        dst = (project(CAM, pose, corners)[0] - 0.5).astype(np.float32)   # OpenCV pixel-centre convention
        h = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(marker, h, (CAM.width, CAM.height), borderValue=(0, 0, 0))
        mask = cv2.warpPerspective(np.full(marker.shape[:2], 255, np.uint8), h, (CAM.width, CAM.height)) > 0
        img[mask] = warped[mask]
    return img


def test_detected_aruco_corners_match_cad_corner_order():
    pose = POSES[1]
    seen = detect_tags(_draw_tags(pose), "DICT_4X4_50")
    assert set(seen) == {0, 1, 2, 3}
    est = solve_pose(seen, _tags(), CAM)
    assert est is not None
    assert np.linalg.norm([est.x - pose.x, est.y - pose.y, est.z - pose.z]) < 0.003   # 3 mm on the table


# --- end to end on the built print model (data/print_model, scripts/build_print_model.py) ---

@pytest.fixture(scope="module")
def model():
    from vision import tabletop

    try:
        return tabletop.load_model()
    except FileNotFoundError:
        pytest.skip("print model not built (uv run python -m scripts.build_print_model)")


def test_true_rise_matches_the_pour_level(model):
    from vision import tabletop

    level = model.scale.level_mm(6.0, model.zref_m)
    assert tabletop.true_reading(model, "cp-0154", level).rise_m == pytest.approx(6.0)


@pytest.mark.parametrize("rise_m", [12.0, 13.0])
def test_synthetic_hover_recovers_rise_at_the_gentle_crossing(model, rise_m):
    """Park Street (cp-0043): tray water reaches it once it overtops the Quinlan sill (~11.5 m); gentle banks give a sharp reading at Tello resolution."""
    from vision import tabletop

    level = model.scale.level_mm(rise_m, model.zref_m)
    reading = tabletop.synthetic_reading(model, "cp-0043", level, seed=1)
    assert reading.rise_m is not None
    assert abs(reading.rise_m - rise_m) < 0.5
    assert reading.rise_lo_m <= rise_m <= reading.rise_hi_m
    assert reading.water_on_road is True


@pytest.mark.parametrize("rise_m", [3.0, 8.0])
def test_bridge_reading_is_honest_on_steep_banks(model, rise_m):
    """The Sidney Baker bluff is steep (x3 exaggerated): 1 px of mask bias is ~1.5 m, so only the range must hold."""
    from vision import tabletop

    level = model.scale.level_mm(rise_m, model.zref_m)
    reading = tabletop.synthetic_reading(model, "cp-0154", level, seed=1)
    assert reading.rise_m is not None
    assert reading.rise_lo_m <= rise_m <= reading.rise_hi_m
    assert reading.confidence != "high"
