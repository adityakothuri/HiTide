"""Live drone routes forward to the Tello bridge; an offline bridge falls back to cached footage."""

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import live_drone

BRIDGE_STATUS = {
    "battery": 88, "temp": 61, "height": 0, "tof": 10, "flight_time": 0, "speed": [0, 0, 0],
    "attitude": [0, 0, 0], "flying": False, "connected": True, "state_age": 0.2, "video_age": 0.1,
    "busy": "", "log": ["05:47:09  Takeoff done, hovering"],
}
GAUGE_STATUS = {
    "gauge": "online", "enabled": True, "running": True, "error": None, "level_mm": 10.0,
    "level_mm_range": [9.0, 11.0], "ft": 3.0, "ft_range": [2.5, 3.5], "confidence": 0.82,
    "crossing_flooded": True, "car_level": "windows", "houses_flooded": 1, "houses_total": 4,
    "visible_cells": 18240, "wet_cells": 6120, "tags_seen": 4, "reproj_err_px": 0.9,
    "has_baseline": True, "simulated": False, "reason": None, "ts": 1762600000.0,
}
OVERLAY_JPEG = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"fake-jpeg" + bytes([0xFF, 0xD9])


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(live_drone.router)
    return TestClient(app)


@pytest.fixture
def bridge(monkeypatch):
    """Fake bridge: records requests and answers like tello_dashboard.py."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/status":
            return httpx.Response(200, json=BRIDGE_STATUS)
        if request.url.path.startswith("/action/") or request.url.path == "/rc":
            return httpx.Response(200, json={"result": "ok"})
        if request.url.path == "/gauge/status":
            return httpx.Response(200, json=GAUGE_STATUS)
        if request.url.path == "/gauge/overlay.jpg":
            return httpx.Response(200, content=OVERLAY_JPEG, headers={"Content-Type": "image/jpeg"})
        if request.method == "POST" and request.url.path.startswith("/gauge/"):
            return httpx.Response(200, json={"result": "ok"})
        return httpx.Response(404, json={"error": "not found"})

    monkeypatch.setattr(live_drone, "_transport", httpx.MockTransport(handler))
    return seen


@pytest.fixture
def offline(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    monkeypatch.setattr(live_drone, "_transport", httpx.MockTransport(handler))


def test_status_offline_bridge_returns_fallback_footage(client, offline):
    body = client.get("/api/live-drone/status").json()
    assert body["bridge"] == "offline"
    assert body["fallback_image_url"].startswith("/static/drone/")
    assert "battery" not in body


def test_status_online_passes_telemetry_through(client, bridge):
    body = client.get("/api/live-drone/status").json()
    assert body["bridge"] == "online"
    assert body["battery"] == 88 and body["connected"] is True
    assert body["fallback_image_url"].startswith("/static/drone/")


def test_status_from_outdated_bridge_is_flagged(client, monkeypatch):
    old = {k: v for k, v in BRIDGE_STATUS.items() if k != "connected"}
    monkeypatch.setattr(live_drone, "_transport", httpx.MockTransport(lambda r: httpx.Response(200, json=old)))
    assert client.get("/api/live-drone/status").json()["bridge"] == "outdated"


@pytest.mark.parametrize("action", ["takeoff", "land", "emergency"])
def test_actions_forward_to_bridge(client, bridge, action):
    response = client.post(f"/api/live-drone/action/{action}")
    assert response.status_code == 200 and response.json() == {"result": "ok"}
    assert bridge[-1].url.path == f"/action/{action}"


def test_unknown_action_rejected_without_reaching_bridge(client, bridge):
    assert client.post("/api/live-drone/action/flip").status_code == 422
    assert bridge == []


def test_rc_forwards_validated_values(client, bridge):
    response = client.post("/api/live-drone/rc", json={"lr": 0, "fb": 50, "ud": -20, "yaw": 0})
    assert response.status_code == 200
    assert bridge[-1].url.path == "/rc"
    assert b'"fb":50' in bridge[-1].content.replace(b" ", b"")


def test_rc_out_of_range_rejected(client, bridge):
    assert client.post("/api/live-drone/rc", json={"fb": 500}).status_code == 422
    assert bridge == []


def test_actions_return_503_when_bridge_offline(client, offline):
    assert client.post("/api/live-drone/action/land").status_code == 503


def test_untrusted_origin_cannot_fly_the_drone(client, bridge):
    response = client.post("/api/live-drone/action/takeoff", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert bridge == []


def test_gauge_status_passes_estimate_through(client, bridge):
    body = client.get("/api/live-drone/gauge").json()
    assert body == GAUGE_STATUS
    assert bridge[-1].url.path == "/gauge/status"


def test_gauge_status_offline_bridge(client, offline):
    response = client.get("/api/live-drone/gauge")
    assert response.status_code == 200 and response.json() == {"gauge": "offline"}


def test_gauge_status_from_bridge_without_gauge_routes_is_offline(client, monkeypatch):
    old = httpx.MockTransport(lambda r: httpx.Response(404, json={"error": "not found"}))
    monkeypatch.setattr(live_drone, "_transport", old)
    assert client.get("/api/live-drone/gauge").json() == {"gauge": "offline"}


def test_gauge_unavailable_is_passed_through(client, monkeypatch):
    unavailable = {"gauge": "unavailable", "enabled": False, "running": False, "error": "ImportError: no cv2"}
    monkeypatch.setattr(live_drone, "_transport",
                        httpx.MockTransport(lambda r: httpx.Response(200, json=unavailable)))
    assert client.get("/api/live-drone/gauge").json()["gauge"] == "unavailable"


@pytest.mark.parametrize("command", ["baseline", "start", "stop"])
def test_gauge_commands_forward_to_bridge(client, bridge, command):
    response = client.post(f"/api/live-drone/gauge/{command}")
    assert response.status_code == 200 and response.json() == {"result": "ok"}
    assert bridge[-1].method == "POST" and bridge[-1].url.path == f"/gauge/{command}"


def test_unknown_gauge_command_rejected_without_reaching_bridge(client, bridge):
    assert client.post("/api/live-drone/gauge/calibrate").status_code == 422
    assert bridge == []


def test_gauge_commands_return_503_when_bridge_offline(client, offline):
    assert client.post("/api/live-drone/gauge/start").status_code == 503


def test_untrusted_origin_cannot_control_the_gauge(client, bridge):
    response = client.post("/api/live-drone/gauge/baseline", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert bridge == []


def test_gauge_overlay_is_proxied_as_uncached_jpeg(client, bridge):
    response = client.get("/api/live-drone/gauge/overlay.jpg")
    assert response.status_code == 200 and response.content == OVERLAY_JPEG
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"


def test_gauge_overlay_404_before_first_reading(client, monkeypatch):
    none_yet = httpx.MockTransport(lambda r: httpx.Response(404, json={"error": "no reading yet"}))
    monkeypatch.setattr(live_drone, "_transport", none_yet)
    assert client.get("/api/live-drone/gauge/overlay.jpg").status_code == 404


def test_gauge_overlay_503_when_bridge_offline(client, offline):
    assert client.get("/api/live-drone/gauge/overlay.jpg").status_code == 503
