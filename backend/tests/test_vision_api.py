"""POST /api/snapshots: validation, origin guard, WS broadcast and fusion into the Hill Country loop."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("osmnx")

T_REPLAY = datetime(2025, 7, 4, 10, 30, tzinfo=timezone.utc).timestamp()


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()
    mp.setenv("PHOTON_MODE", "mock")
    mp.setenv("EVIDENCE_POLL_SECONDS", "0")
    mp.setenv("HITIDE_DB_BACKEND", "sqlite")
    from app.main import app

    with TestClient(app) as c:
        yield c
    mp.undo()


def _snap(**kw):
    base = {"point_id": "photo-1", "time": datetime.now(timezone.utc).isoformat(), "water_on_road": True,
            "est_depth_in": 14.0, "depth_method": "water_edge_dem", "rising": None, "people_seen": 0,
            "confidence": "medium", "source": "photo"}
    return {**base, **kw}


def test_untrusted_origin_is_rejected(client):
    r = client.post("/api/snapshots", json=_snap(), headers={"origin": "https://evil.invalid"})
    assert r.status_code == 403


@pytest.mark.parametrize("bad", [
    {"est_depth_in": "NaN"},
    {"image_url": "/static/drone/../../backend/.env"},
    {"image_url": "/static/drone/snapshots/does-not-exist.jpg"},
    {"people_seen": 3},
    {"point_id": "a" * 65},
    {"vehicles": [{"track_id": 1, "type": "car", "in_water": True}] * 51},
])
def test_bad_snapshots_are_rejected(client, bad):
    assert client.post("/api/snapshots", json=_snap(**bad)).status_code == 422


def test_snapshot_is_broadcast_as_snapshot_created(client):
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "snapshot"
        r = client.post("/api/snapshots", json=_snap())
        assert r.status_code == 202 and r.json()["fused"] is False
        msg = ws.receive_json()
        while msg["type"] != "snapshot.created":
            msg = ws.receive_json()
    assert msg["payload"]["point_id"] == "photo-1" and msg["payload"]["est_depth_in"] == 14.0


def test_unknown_water_on_road_is_never_fused(client):
    r = client.post("/api/snapshots", json=_snap(point_id="cp-0014", water_on_road=None, est_depth_in=None,
                                                  depth_method="none"))
    assert r.status_code == 202
    assert r.json()["fused"] is False and "never treated as dry" in r.json()["not_fused_reason"]


def test_wet_snapshot_confirms_the_critical_point_in_the_running_replay(client):
    # the hill runtime lives on the app's event loop: build it through the API, then reach it via app.state
    assert client.get("/api/region/state").status_code == 200
    hill = client.app.state.hill_task.result()
    loop = hill.loop
    with loop.lock:
        loop.reset_state()
    loop.step(T_REPLAY)
    r = client.post("/api/snapshots", json=_snap(point_id="cp-0014", source="synthetic"))
    assert r.status_code == 202 and r.json()["fused"] is True
    loop.step(T_REPLAY + 60)
    assert loop.status["cp-0014"] == "confirmed_flooded"
    assert loop.obs["cp-0014"].est_depth_in == 14.0
    with loop.lock:
        loop.reset_state()


def test_wet_snapshot_without_a_depth_does_not_break_the_loop_step(client):
    """Regression: the loop compares est_depth_in >= 24 on every tick; a null depth must not crash it."""
    assert client.get("/api/region/state").status_code == 200
    loop = client.app.state.hill_task.result().loop
    with loop.lock:
        loop.reset_state()
    loop.step(T_REPLAY)
    r = client.post("/api/snapshots", json=_snap(point_id="cp-0014", est_depth_in=None, depth_method="none"))
    assert r.json()["fused"] is True
    loop.step(T_REPLAY + 60)                                   # must not raise
    assert loop.status["cp-0014"] == "confirmed_flooded"
    with loop.lock:
        loop.reset_state()


def test_oversized_reason_strings_are_rejected(client):
    assert client.post("/api/snapshots", json=_snap(confidence_reasons=["x" * 500])).status_code == 422
