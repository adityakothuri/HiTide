"""Regression checks for live segmentation instead of preset overlays."""
import sys
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_overlay import LiveAnalysis, detect_water


def test_water_regions_follow_changed_pixels_without_anchor():
    frame = np.full((720, 960, 3), 160, np.uint8)
    assert detect_water(frame)["polygons"] == []
    frame[150:350, 200:500] = [0, 160, 190]
    first = detect_water(frame)
    assert first["polygons"]
    assert abs(first["coverage_pct"] - 8.7) < 0.2
    moved = np.full_like(frame, 160)
    moved[300:500, 400:700] = [0, 160, 190]
    second = detect_water(moved)
    assert np.min(second["polygons"][0], axis=0).tolist() == [400, 300]
    assert first["polygons"] != second["polygons"]


def test_water_disappears_and_stale_frame_keeps_timestamp():
    current = [np.full((720, 960, 3), [0, 160, 190], np.uint8)]
    records = []
    analyzer = LiveAnalysis(lambda: current[0], lambda *a, **kw: records.append(kw))
    first = analyzer.status()
    assert first["polygons"]
    assert analyzer.status()["ts"] == first["ts"]
    assert len(records) == 1
    current[0] = np.full_like(current[0], 160)
    assert analyzer.status()["polygons"] == []
    assert len(records) == 2


def test_no_frame_reports_unavailable():
    result = LiveAnalysis(lambda: None, lambda *a, **kw: None).status()
    assert result["polygons"] == []
    assert result["age_s"] is None



def test_boxes_acquire_without_a_depth_reading_and_reject_collapsed_tray():
    from live_overlay import FrameOverlay
    renderer = FrameOverlay()
    frame = np.full((720, 960, 3), 150, np.uint8)
    geometry = {"tray_polygon": [[200, 400], [300, 300], [550, 350], [550, 500]],
                "car_polygon": [[370, 380], [400, 380], [400, 400], [370, 400]]}
    renderer.seed_geometry(frame, geometry)
    assert set(renderer.regions) == {"car", "tray"}
    rejected = FrameOverlay()
    geometry["tray_polygon"] = [[760, 520], [850, 630], [920, 710], [830, 600]]
    rejected.seed_geometry(frame, geometry)
    assert rejected.regions == {}
