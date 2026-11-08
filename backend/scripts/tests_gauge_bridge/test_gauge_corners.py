"""POST /gauge/corners on the bridge: tag-free pose from 4 clicked tray corners."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
dash = pytest.importorskip("tello_dashboard")

POINTS = [[100, 400], [700, 420], [620, 180], [180, 170]]


class FakeReader:
    def __init__(self):
        self.corners = None

    def set_corners(self, points):
        self.corners = points
        return True, "ok"

    def clear_corners(self):
        self.corners = None

    def set_baseline(self, frame):
        return True, "ok"

    def update(self, frame):
        return None

    def overlay(self, frame, estimate):
        return frame


class OldReader(FakeReader):
    set_corners = None  # a gauge build from before tag-free pose


def service(reader):
    svc = dash.GaugeService(lambda: None, reader_factory=lambda: reader, note=lambda text: None)
    svc.preload()
    return svc


@pytest.mark.parametrize("body,problem", [({}, "send 4 points"), ({"points": POINTS[:3]}, "send 4 points"),
                                          ({"points": [[1, "x"]] * 4}, "numbers"), ({"points": [[-5, 1]] * 4}, "inside")])
def test_bad_corner_bodies_are_rejected(body, problem):
    data, code = dash.gauge_action(service(FakeReader()), "corners", body)
    assert code == 400 and problem in data["error"]


def test_corners_set_and_clear():
    reader = FakeReader()
    svc = service(reader)
    assert dash.gauge_action(svc, "corners", {"points": POINTS}) == ({"result": "ok"}, 200)
    assert reader.corners == [[100.0, 400.0], [700.0, 420.0], [620.0, 180.0], [180.0, 170.0]]
    assert svc.status()["corners"] == reader.corners
    assert dash.gauge_action(svc, "corners", {"clear": True}) == ({"result": "ok"}, 200)
    assert reader.corners is None and svc.status()["corners"] is None


def test_old_gauge_build_says_it_cannot_use_corners():
    data, code = dash.gauge_action(service(OldReader()), "corners", {"points": POINTS})
    assert code == 200 and "can't use tray corners" in data["result"]
