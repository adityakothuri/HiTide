"""GaugeService in the Tello bridge, with a fake reader: no drone, no real gauge package needed.

Run: ~/tello-env/Scripts/python.exe -m pytest backend/scripts/tests_gauge_bridge -q -p no:cacheprovider
"""

from __future__ import annotations

import importlib
import json
import sys
import threading
import time
import types
from pathlib import Path

import numpy as np
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))


def _stub_missing(name: str, **attrs: object) -> None:
    """The bridge imports cv2 and djitellopy at module level; stand in when they're not installed."""
    try:
        importlib.import_module(name)
    except ImportError:
        sys.modules[name] = types.SimpleNamespace(**attrs)  # type: ignore[assignment]


_stub_missing("cv2", IMWRITE_JPEG_QUALITY=1)
_stub_missing("djitellopy", Tello=object)

import tello_dashboard as td

WAIT_S = 2.0
FAST = 0.01


class FakeEstimate:
    def __init__(self, ft: float | None, reason: str | None = None) -> None:
        self.ft, self.reason = ft, reason

    def to_dict(self) -> dict:
        return {"ft": np.float64(self.ft) if self.ft is not None else None,
                "ft_range": (np.float64(2.5), np.float64(3.5)) if self.ft is not None else None,
                "car_level": "windows", "tags_seen": np.int64(4), "reason": self.reason,
                "has_baseline": False, "simulated": True}


class FakeReader:
    def __init__(self, fail_update: bool = False, baseline_ok: bool = True) -> None:
        self.fail_update, self.baseline_ok = fail_update, baseline_ok
        self.baselines: list[np.ndarray] = []
        self.updates: list[np.ndarray] = []

    def set_baseline(self, frame: np.ndarray) -> tuple[bool, str]:
        self.baselines.append(frame)
        return (True, "") if self.baseline_ok else (False, "only 2 tags visible")

    def update(self, frame: np.ndarray) -> FakeEstimate:
        if self.fail_update:
            raise RuntimeError("glare blew out the tags")
        self.updates.append(frame)
        return FakeEstimate(3.0)

    def overlay(self, frame: np.ndarray, estimate: FakeEstimate) -> np.ndarray:
        return frame


class FrameFeed:
    """Hands out a new RGB frame object per call, like djitellopy's frame reader."""

    def __init__(self, available: bool = True) -> None:
        self.available = available

    def __call__(self) -> np.ndarray | None:
        if not self.available:
            return None
        frame = np.zeros((4, 4, 3), dtype=np.uint8)
        frame[..., 0] = 200  # red channel in RGB
        return frame


def make_service(reader: FakeReader | None = None, factory=None, feed: FrameFeed | None = None):
    notes: list[str] = []
    service = td.GaugeService(
        frame_source=feed or FrameFeed(), note=notes.append,
        reader_factory=factory or (lambda: reader or FakeReader()),
        encoder=lambda frame: b"jpeg", interval=FAST,
    )
    return service, notes


def wait_for(condition, timeout: float = WAIT_S) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(FAST)
    return False


def test_start_reads_until_stopped():
    reader = FakeReader()
    service, _ = make_service(reader)
    assert service.start() == "ok"
    assert wait_for(lambda: service.estimate.get("ft") == 3.0)
    status = service.status()
    assert status["gauge"] == "online" and status["enabled"] and status["running"]
    assert status["ft_range"] == [2.5, 3.5] and status["tags_seen"] == 4
    assert service.overlay_jpeg == b"jpeg"
    json.dumps(status)  # numpy scalars were converted

    assert service.stop() == "ok"
    assert wait_for(lambda: not service.running)
    count = len(reader.updates)
    time.sleep(FAST * 10)
    assert len(reader.updates) == count
    assert service.status()["ft"] == 3.0  # the last estimate stays visible


def test_frames_are_converted_rgb_to_bgr():
    reader = FakeReader()
    service, _ = make_service(reader)
    service.start()
    assert wait_for(lambda: reader.updates)
    service.stop()
    assert reader.updates[0][0, 0].tolist() == [0, 0, 200]


def test_status_before_any_reading_has_null_estimate():
    service, _ = make_service()
    service._ensure_reader()
    status = service.status()
    assert status["gauge"] == "online" and not status["enabled"] and not status["running"]
    assert status["ft"] is None and status["car_level"] is None and status["has_baseline"] is False
    assert set(td.ESTIMATE_FIELDS) <= set(status)


def test_baseline_captured_from_current_frame():
    reader = FakeReader()
    service, notes = make_service(reader)
    assert service.capture_baseline() == "ok"
    assert len(reader.baselines) == 1 and reader.baselines[0][0, 0].tolist() == [0, 0, 200]
    assert service.status()["has_baseline"] is True
    assert any("baseline captured" in n for n in notes)


def test_baseline_refusal_reason_is_returned():
    service, _ = make_service(FakeReader(baseline_ok=False))
    assert service.capture_baseline() == "only 2 tags visible"
    assert service.status()["has_baseline"] is False


def test_baseline_without_video_is_refused():
    service, _ = make_service(feed=FrameFeed(available=False))
    assert service.capture_baseline() == "no video frame yet"


def test_reader_errors_are_contained_and_logged_once():
    service, notes = make_service(FakeReader(fail_update=True))
    service.start()
    assert wait_for(lambda: service.error is not None)
    service.read_once(np.zeros((4, 4, 3), dtype=np.uint8))  # same error again
    service.stop()
    assert "glare blew out the tags" in service.status()["error"]
    assert sum("glare" in n for n in notes) == 1


def test_missing_gauge_package_reports_unavailable():
    def broken():
        raise ImportError("No module named 'gauge'")

    service, notes = make_service(factory=broken)
    assert service.start().startswith("gauge unavailable")
    assert service.capture_baseline().startswith("gauge unavailable")
    assert wait_for(lambda: service.status()["gauge"] == "unavailable" and service.status()["error"])
    status = service.status()
    assert "No module named 'gauge'" in status["error"] and not status["running"]
    assert any("unavailable" in n for n in notes)


def test_status_never_blocks_while_the_model_loads():
    release = threading.Event()

    def slow_factory():
        release.wait(WAIT_S)
        return FakeReader()

    service, _ = make_service(factory=slow_factory)
    started = time.time()
    status = service.status()
    assert time.time() - started < 0.5
    assert status["gauge"] == "unavailable" and status["error"] == td.GAUGE_LOADING
    release.set()
    assert wait_for(lambda: service.status()["gauge"] == "online")


def test_gauge_action_routes():
    service, _ = make_service()
    assert td.gauge_action(None, "start") == ({"error": "gauge not running in this dashboard"}, 503)
    assert td.gauge_action(service, "calibrate")[1] == 404
    assert td.gauge_action(service, "start") == ({"result": "ok"}, 200)
    assert td.gauge_action(service, "stop") == ({"result": "ok"}, 200)


def test_real_default_factory_failure_is_unavailable(monkeypatch):
    """The real lazy import: a broken `gauge` module must not escape."""
    monkeypatch.setitem(sys.modules, "gauge", None)  # makes `import gauge...` raise ImportError
    monkeypatch.setitem(sys.modules, "gauge.camera", None)
    service = td.GaugeService(frame_source=FrameFeed(), note=lambda _: None, interval=FAST)
    assert service.start().startswith("gauge unavailable")


@pytest.mark.parametrize("value, expected", [
    ({"a": (np.float32(1.5), np.int64(2))}, {"a": [1.5, 2]}),
    (np.array([1, 2]), [1, 2]),
    (None, None),
])
def test_jsonable(value, expected):
    assert td.jsonable(value) == expected


def test_button_press_retries_a_failed_load():
    attempts: list[int] = []

    def flaky():
        attempts.append(1)
        if len(attempts) == 1:
            raise ImportError("No module named 'gauge.water'")
        return FakeReader()

    service, _ = make_service(factory=flaky)
    assert service.start().startswith("gauge unavailable")
    assert service.status()["gauge"] == "unavailable"  # polling alone does not retry
    assert service.start() == "ok"
    assert service.status()["gauge"] == "online"
    service.stop()
