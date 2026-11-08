"""Tello hookup: scale a planned leg to safe indoor moves, detect the blue-sheet 'water' (overview 9.2-9.4)."""

from __future__ import annotations

import numpy as np
import pytest

from drone.tello import MAX_MOVE_CM, MIN_MOVE_CM, blue_sheet_cover_pct, indoor_moves


def test_long_real_leg_is_scaled_to_a_short_indoor_flight():
    # 5 km due north in the real plan -> at most MAX_MOVE_CM forward, no rotation
    moves = indoor_moves(bearing_deg=0.0, distance_m=5000.0)
    assert moves[0] == ("rotate", 0) or moves[0][0] == "forward"
    fwd = sum(v for k, v in moves if k == "forward")
    assert MIN_MOVE_CM <= fwd <= MAX_MOVE_CM


def test_bearing_becomes_a_clockwise_rotation_in_range():
    moves = indoor_moves(bearing_deg=270.0, distance_m=800.0)
    rot = [v for k, v in moves if k == "rotate"]
    assert rot and rot[0] == -90  # shortest turn: 90 deg counter-clockwise


def test_moves_are_integers_within_tello_limits():
    for k, v in indoor_moves(bearing_deg=123.4, distance_m=1234.5):
        assert isinstance(v, int)
        if k == "forward":
            assert MIN_MOVE_CM <= v <= MAX_MOVE_CM  # Tello SDK accepts 20-500 cm; we cap lower indoors


def test_blue_sheet_detector_measures_cover():
    frame = np.full((100, 200, 3), (60, 60, 60), dtype=np.uint8)   # grey "road" (BGR)
    frame[:, :100] = (200, 80, 20)                                  # left half blue sheet
    assert blue_sheet_cover_pct(frame) == pytest.approx(50, abs=2)
    assert blue_sheet_cover_pct(np.full((50, 50, 3), 60, dtype=np.uint8)) == 0


class _FakeTello:
    def __init__(self, frames):
        self.calls, self._frames = [], iter(frames)

    def __getattr__(self, name):
        def call(*a):
            self.calls.append(name)
        return call

    def get_frame_read(self):
        outer = self

        class _R:
            @property
            def frame(self):
                return next(outer._frames, None)
        return _R()


def test_lost_video_lands_and_fails_the_task(monkeypatch):
    import drone.tello as t
    monkeypatch.setattr(t, "FRAME_EVERY_S", 0.0)
    fake = _FakeTello([np.full((10, 10, 3), 60, dtype=np.uint8)])  # one frame, then video drops
    res = t.fly_first_leg(90.0, 1000.0, tello=fake)
    assert res.ok is False and res.error == "video lost"
    assert "land" in fake.calls and fake.calls.index("takeoff") < fake.calls.index("land")
