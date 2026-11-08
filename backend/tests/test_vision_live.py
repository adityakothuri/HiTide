"""Drone -> vision bridge: Tello hover frames become a VisionSnapshot that reaches the loop and the WS."""

from datetime import datetime, timezone

import numpy as np
import pytest

from vision.config import vision_config
from vision.detect import Det
from vision.grid import Seg
from vision.live import hover_snapshot
from vision.pipeline import StepInput

CFG = vision_config()
T0 = datetime(2025, 7, 4, 10, 30, tzinfo=timezone.utc).timestamp()
STEP = StepInput(T0, drone_id="tello-1", source="live", simulated=False)


def _seg(water_rows: int, h: int = 200, w: int = 300) -> Seg:
    p = np.zeros((h, w), np.float32)
    p[h - water_rows:] = 0.9
    return Seg(np.full((h, w), 13, np.int16), p)


def test_hover_votes_water_over_frames_and_one_glitch_frame_does_not_flip_it():
    segs = [_seg(120)] * 6 + [_seg(0)]                        # 60% water, last frame drops out
    snap = hover_snapshot("cp-0014", segs, [], STEP, CFG)
    assert snap.water_on_road is True and snap.source == "live" and snap.simulated is False
    assert any("hover: 7 frames" in r for r in snap.confidence_reasons)
    assert "single frame (no tracking)" not in snap.confidence_reasons


def test_hover_without_water_is_unknown_never_dry():
    snap = hover_snapshot("cp-0014", [_seg(0)] * 5, [], STEP, CFG)
    assert snap.water_on_road is None and snap.est_depth_in is None


def test_live_hover_never_estimates_depth_even_with_a_half_sunk_car():
    car = Det(3, "car", 0.9, (100.0, 100.0, 200.0, 121.0))
    snap = hover_snapshot("cp-0014", [_seg(100)] * 5, [car], STEP, CFG)
    assert snap.water_on_road is True and snap.depth_method == "none" and snap.est_depth_in is None
    assert snap.vehicles[0].in_water and snap.vehicles[0].band is None
    assert snap.alerts and snap.alerts[0].boat_required          # unknown depth -> boat


def test_empty_hover_is_rejected():
    with pytest.raises(ValueError):
        hover_snapshot("cp-0014", [], [], STEP, CFG)


class _FakeTello:
    def __init__(self, frames):
        self.calls, self._frames = [], frames

    def __getattr__(self, name):
        def call(*a):
            self.calls.append(name)
        return call

    def get_frame_read(self):
        frames = self._frames

        class _R:
            frame = frames[0]
        return _R()


def test_tello_hover_hands_bgr_keyframes_to_the_vision_model(monkeypatch):
    import drone.tello as t

    monkeypatch.setattr(t, "HOVER_S", 0.05)
    monkeypatch.setattr(t, "FRAME_EVERY_S", 0.005)
    rgb = np.zeros((20, 30, 3), np.uint8)
    rgb[..., 2] = 200                                           # blue in RGB
    res = t.fly_first_leg(0.0, 500.0, tello=_FakeTello([rgb]))
    assert res.ok and res.keyframes
    assert len(res.keyframes) == -(-res.frames // t.KEEP_EVERY)
    assert res.keyframes[0][0, 0, 0] == 200 and res.keyframes[0][0, 0, 2] == 0   # converted to BGR
    assert res.water_on_road is True


# ---------- route: POST /api/region/drones/tello with the vision model stubbed ----------

@pytest.fixture(scope="module")
def client():
    pytest.importorskip("osmnx")
    from fastapi.testclient import TestClient

    mp = pytest.MonkeyPatch()
    mp.setenv("PHOTON_MODE", "mock")
    mp.setenv("EVIDENCE_POLL_SECONDS", "0")
    mp.setenv("HITIDE_DB_BACKEND", "sqlite")
    from app.main import app

    with TestClient(app) as c:
        yield c
    mp.undo()


def test_tello_flight_runs_the_vision_model_and_fuses_into_the_loop(client, monkeypatch):
    import drone.tello as tello
    import vision.live as live

    assert client.get("/api/region/state").status_code == 200
    loop = client.app.state.hill_task.result().loop
    with loop.lock:
        loop.reset_state()
    loop.step(T0)
    drone = next((d for d in loop.drones.values() if d.target), None)
    if drone is None:
        pytest.skip("no drone target at this replay time")
    frames = (np.zeros((20, 30, 3), np.uint8),) * 6
    monkeypatch.setenv("DRONE_MODE", "tello")
    monkeypatch.setattr(tello, "fly_first_leg",
                        lambda b, d: tello.TelloResult(True, 40, True, 12, keyframes=frames))
    seen = {}

    def fake_run_hover(fr, point_id, drone_id, t, color_fallback=True):
        seen["n"] = len(fr)
        step = StepInput(t, drone_id=drone_id, source="live", simulated=False)
        return hover_snapshot(point_id, [_seg(120)] * len(fr), [], step, CFG)

    monkeypatch.setattr(live, "run_hover", fake_run_hover)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        r = client.post("/api/region/drones/tello")
        body = r.json()
        msg = ws.receive_json()
        while msg["type"] != "snapshot.created":
            msg = ws.receive_json()
    assert r.status_code == 200 and body["ok"] and body["vision"] and body["fused"] is True
    assert seen["n"] == 6 and msg["payload"]["source"] == "live"
    target = body["snapshot"]["point_id"]
    assert loop.obs[target].water_on_road is True and loop.obs[target].simulated is False
    with loop.lock:
        loop.reset_state()


def test_tello_flight_falls_back_to_hsv_cover_without_the_vision_model(client, monkeypatch):
    import drone.tello as tello

    loop = client.app.state.hill_task.result().loop
    with loop.lock:
        loop.reset_state()
    loop.step(T0)
    if next((d for d in loop.drones.values() if d.target), None) is None:
        pytest.skip("no drone target at this replay time")
    monkeypatch.setenv("DRONE_MODE", "tello")
    monkeypatch.setenv("TELLO_VISION", "0")
    monkeypatch.setattr(tello, "fly_first_leg", lambda b, d: tello.TelloResult(True, 40, True, 12))
    body = client.post("/api/region/drones/tello").json()
    assert body["ok"] and body["vision"] is False and body["snapshot"]["water_on_road"] is True
    with loop.lock:
        loop.reset_state()
