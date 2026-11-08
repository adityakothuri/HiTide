import json
import time
from dataclasses import replace

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from gauge.camera import Intrinsics, tello_default  # noqa: E402
from gauge.model import level_mm, load_tray  # noqa: E402
from gauge.synth import Noise, look_at_pose, render  # noqa: E402
from gauge.tests.sweep import (EXACT_FT, HOVER_FT, HOVER_POSES, MID_STEP_FT, NOISE, STAND_POSES,  # noqa: E402
                               none_rate, rate, run_sweep)
from gauge.water import (CAR_LEVELS, GaugeReader, WaterEstimate, _apply_car_hysteresis,  # noqa: E402
                         car_level_index, describe_level)

CAM = tello_default()


@pytest.fixture(scope="module")
def model():
    return load_tray()


@pytest.fixture(scope="module")
def stand_mid(model):
    return run_sweep(model, "stand", STAND_POSES, MID_STEP_FT)


@pytest.fixture(scope="module")
def stand_exact(model):
    return run_sweep(model, "stand-exact", STAND_POSES[:3], EXACT_FT)


@pytest.fixture(scope="module")
def hover(model):
    return run_sweep(model, "hover", HOVER_POSES, HOVER_FT)


# ------------------------------------------------------------------ accuracy sweeps
def test_stand_mid_step_with_baseline_within_half_foot(stand_mid):
    assert rate(stand_mid, 0.5, baseline=True) >= 0.9


def test_stand_mid_step_without_baseline_within_one_foot(stand_mid):
    assert rate(stand_mid, 1.0, baseline=False) >= 0.9
    assert none_rate(stand_mid, baseline=False) <= 0.1


def test_stand_exact_levels_within_one_step(stand_exact):
    assert rate(stand_exact, 1.0, baseline=True) >= 0.9
    assert rate(stand_exact, 1.0, baseline=False) >= 0.9


def test_hover_is_within_a_foot_or_none_and_never_confidently_wrong(hover):
    for case in hover:
        if case.ft_est is None:
            assert case.confidence == 0.0
        elif case.error > 1.0:
            assert case.confidence < 0.5, case


def test_reading_from_a_wrong_focal_guess(model):
    true_cam = Intrinsics(683.0, 683.0, 480.0, 360.0)
    pose = look_at_pose(model, 380, 50, 20)
    rng = np.random.default_rng(11)
    dry = render(model, true_cam, pose, None, noise=Noise.modest(), rng=rng)
    reader = GaugeReader(model, Intrinsics(920.0, 920.0, 480.0, 360.0))
    assert reader.set_baseline(dry)[0]
    errors = []
    for ft in (1.5, 3.5, 5.5):
        est = reader.read(render(model, true_cam, pose, level_mm(model, ft), noise=Noise.modest(), rng=rng))
        assert est.ft is not None
        errors.append(abs(est.ft - ft))
        assert est.focal_px == pytest.approx(683.0, rel=0.1)
    assert max(errors) <= 0.5


def test_reader_with_matching_camera_reports_step_range(model):
    pose = look_at_pose(model, 400, 50, 0)
    reader = GaugeReader(model, CAM)
    est = reader.read(render(model, CAM, pose, level_mm(model, 3.5), noise=Noise.modest()))
    assert est.ft == pytest.approx(3.5) and est.ft_range == (3.0, 4.0)
    assert est.level_mm_range == pytest.approx((10.0, 12.0))
    assert est.simulated is False and est.tags_seen >= 3 and 0.0 < est.confidence <= 1.0


# ------------------------------------------------------------------ failure modes
def test_dry_tray_reports_no_water(model):
    reader = GaugeReader(model, CAM)
    est = reader.read(render(model, CAM, look_at_pose(model, 400, 50, 0), None, noise=Noise.modest()))
    assert est.ft is None and est.reason is not None and est.confidence == 0.0


def test_missing_tags_give_none_with_reason(model):
    pose = look_at_pose(model, 400, 50, 0)
    frame = render(model, CAM, pose, level_mm(model, 3.5))
    frame[:, :] = frame[:, :] // 3 + 120  # washed out, tags unreadable
    reader = GaugeReader(model, CAM)
    est = reader.read(np.full((720, 960, 3), 150, np.uint8))
    assert est.ft is None and "tags" in est.reason
    assert reader.read(None).reason == "no frame"


def test_invalid_dye_rejected(model):
    with pytest.raises(ValueError):
        GaugeReader(model, CAM, dye="purple")


def test_baseline_rejected_without_tags(model):
    ok, reason = GaugeReader(model, CAM).set_baseline(np.full((720, 960, 3), 90, np.uint8))
    assert not ok and "tags" in reason


def test_baseline_moved_is_reported_not_used(model):
    rng = np.random.default_rng(4)
    pose_a = look_at_pose(model, 380, 50, 20)
    pose_b = look_at_pose(model, 430, 50, 20)
    reader = GaugeReader(model, CAM)
    assert reader.set_baseline(render(model, CAM, pose_a, None, noise=Noise.modest(), rng=rng)) == (True, "ok")
    same = reader.read(render(model, CAM, pose_a, level_mm(model, 3.5), noise=Noise.modest(), rng=rng))
    assert same.has_baseline and not same.baseline_moved
    moved = reader.read(render(model, CAM, pose_b, level_mm(model, 3.5), noise=Noise.modest(), rng=rng))
    assert moved.baseline_moved and not moved.has_baseline
    assert moved.reason is not None and "baseline" in moved.reason


# ------------------------------------------------------------------ meaning
def test_meaning_at_known_levels(model):
    expect = {  # ft -> (crossing flooded, car level, houses flooded)
        0: (False, "none", 0), 1: (True, "none", 0), 2: (True, "doors", 4), 3: (True, "windows", 8),
        4: (True, "roof", 9), 6: (True, "roof", 10),
    }
    for ft, want in expect.items():
        assert describe_level(model, level_mm(model, ft)) == want, ft


def test_car_level_boundaries(model):
    car = model.car
    assert CAR_LEVELS[car_level_index(model, car.road_mm - 0.01)] == "none"
    assert CAR_LEVELS[car_level_index(model, car.road_mm + 0.5)] == "wheels"
    assert CAR_LEVELS[car_level_index(model, car.road_mm + 1.0)] == "doors"
    assert CAR_LEVELS[car_level_index(model, car.body_top_mm + 0.1)] == "windows"
    assert CAR_LEVELS[car_level_index(model, car.roof_mm + 0.1)] == "roof"


def test_car_hysteresis_needs_margin(model):
    car = model.car
    idx_none = car_level_index(model, 5.0)
    assert _apply_car_hysteresis(model, car.road_mm + 0.1, idx_none) == idx_none
    assert _apply_car_hysteresis(model, car.road_mm + 0.4, idx_none) == idx_none + 1
    wheels = idx_none + 1
    assert _apply_car_hysteresis(model, car.road_mm - 0.1, wheels) == wheels
    assert _apply_car_hysteresis(model, car.road_mm - 0.4, wheels) == idx_none
    assert _apply_car_hysteresis(model, 8.0, None) == car_level_index(model, 8.0)


# ------------------------------------------------------------------ temporal smoothing (fake reads)
def fake_estimate(model, ft, wet_fraction, tags=4):
    centre = level_mm(model, ft)
    return WaterEstimate(level_mm=centre, level_mm_range=(centre - 1.0, centre + 1.0), ft=ft,
                         ft_range=(ft - 0.5, ft + 0.5), confidence=0.9, tags_seen=tags,
                         wet_fraction=wet_fraction, houses_total=len(model.houses), has_baseline=True)


def scripted_reader(model, estimates):
    reader = GaugeReader(model, CAM)
    queue = iter(estimates)
    reader.read = lambda frame: next(queue)  # type: ignore[method-assign]
    return reader


def test_single_outlier_frame_is_rejected(model):
    good = fake_estimate(model, 3.5, 0.70)
    outlier = fake_estimate(model, 5.5, 0.74)  # plausible wet fraction, so only the median can reject it
    reader = scripted_reader(model, [good] * 5 + [outlier] + [good])
    results = [reader.update(None) for _ in range(7)]
    assert all(r.ft == pytest.approx(3.5) for r in results)


def test_wet_fraction_jump_is_dropped(model):
    good = fake_estimate(model, 3.5, 0.50)
    hand = fake_estimate(model, 6.5, 0.95)
    reader = scripted_reader(model, [good] * 4 + [hand, good])
    results = [reader.update(None) for _ in range(6)]
    assert results[4].ft == pytest.approx(3.5) and "dropped" in results[4].reason
    assert results[5].ft == pytest.approx(3.5)


def test_persistent_change_is_eventually_accepted(model):
    old, new = fake_estimate(model, 2.5, 0.40), fake_estimate(model, 6.5, 0.95)
    reader = scripted_reader(model, [old] * 4 + [new] * 12)
    results = [reader.update(None) for _ in range(16)]
    assert results[-1].ft == pytest.approx(6.5)


def test_occluded_frames_do_not_pull_the_median(model):
    good = fake_estimate(model, 3.5, 0.70)
    hidden = WaterEstimate(reason="only 1 of 4 tags visible", tags_seen=1)
    reader = scripted_reader(model, [good] * 3 + [hidden] * 3 + [good])
    results = [reader.update(None) for _ in range(7)]
    assert all(r.ft == pytest.approx(3.5) for r in results)
    assert "tags" in results[3].reason
    assert reader.update.__self__._buffer.maxlen == 8 and len(reader._buffer) == 4


def test_update_without_history_passes_none_through(model):
    reader = scripted_reader(model, [WaterEstimate(reason="only 0 of 4 tags visible")])
    assert reader.update(None).ft is None


def test_car_level_hysteresis_in_update(model):
    low, high = fake_estimate(model, 1.5, 0.30), fake_estimate(model, 2.0, 0.30)
    # centres 7.0 mm (wheels) and 8.0 mm (doors): doors clears road+1.0 = 7.98 by only 0.02
    reader = scripted_reader(model, [low] * 3 + [high] * 6)
    results = [reader.update(None) for _ in range(9)]
    assert results[2].car_level == "wheels"
    assert results[-1].car_level == "wheels"  # 8.0 mm has not cleared 7.98 + 0.3
    big = fake_estimate(model, 3.0, 0.30)
    reader = scripted_reader(model, [low] * 3 + [big] * 6)
    assert [reader.update(None) for _ in range(9)][-1].car_level == "windows"


def test_reset_clears_history(model):
    reader = scripted_reader(model, [fake_estimate(model, 3.5, 0.7), WaterEstimate(reason="x")])
    reader.update(None)
    reader.reset()
    assert reader.update(None).ft is None


# ------------------------------------------------------------------ misc
def test_update_on_real_frames_and_runtime(model):
    pose = look_at_pose(model, 380, 50, 20)
    rng = np.random.default_rng(9)
    reader = GaugeReader(model, CAM)
    reader.set_baseline(render(model, CAM, pose, None, noise=NOISE, rng=rng))
    frames = [render(model, CAM, pose, level_mm(model, 4.5), noise=NOISE, rng=rng) for _ in range(3)]
    start = time.perf_counter()
    results = [reader.update(f) for f in frames]
    per_frame = (time.perf_counter() - start) / len(frames)
    assert per_frame < 1.0
    assert results[-1].ft == pytest.approx(4.5) and results[-1].car_level == "roof"


def test_to_dict_is_json_serialisable(model):
    payload = json.dumps(fake_estimate(model, 3.5, 0.5).to_dict())
    assert json.loads(payload)["ft_range"] == [3.0, 4.0]


def test_overlay_marks_frame_and_keeps_input(model):
    pose = look_at_pose(model, 400, 50, 0)
    frame = render(model, CAM, pose, level_mm(model, 3.5))
    original = frame.copy()
    reader = GaugeReader(model, CAM)
    est = replace(reader.read(frame), simulated=True)
    out = reader.overlay(frame, est)
    assert out.shape == frame.shape and not np.array_equal(out, frame)
    assert np.array_equal(frame, original)
    assert reader.overlay(frame, WaterEstimate(reason="no frame")).shape == frame.shape
