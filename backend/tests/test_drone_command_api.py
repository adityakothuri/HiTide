"""POST /api/drones/{id}/command: logs the action on the case, 'return' recalls the drone, unknown -> 404."""

import pytest
from fastapi.testclient import TestClient

from drone.dispatch import Drone
from scoring.risk import RiskScore
from stages.escalation import open_case

pytest.importorskip("osmnx")


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()
    mp.setenv("PHOTON_MODE", "mock")
    mp.setenv("EVIDENCE_POLL_SECONDS", "0")
    mp.setenv("FLOODWATCH_DB_BACKEND", "sqlite")
    from app.main import app

    with TestClient(app) as c:
        yield c
    mp.undo()


def _seed(client) -> None:
    runner = client.app.state.runtime.runner
    risk = RiskScore(value=0.8, reasons=(), high_risk=True, notify_parent=False, factors={})
    runner.world.cases["case-x"] = open_case("case-x", "d-001", "Dana", 30.05, -99.14, 8.0, risk,
                                             "2026-11-08T09:00:00+00:00")
    runner.world.case_opened_s["case-x"] = runner.engine.t_sim_s
    runner.world.drones["case-x"] = Drone("drone-case-x", "case-x", 30.04, -99.13, 30.05, -99.14,
                                          runner.engine.t_sim_s, 15.0)


def test_speak_adds_timeline_entry(client):
    _seed(client)
    r = client.post("/api/drones/drone-case-x/command", json={"command": "speak"})
    assert r.status_code == 200
    assert r.json()["timeline"][-1]["kind"] == "drone"
    assert "loudspeaker" in r.json()["timeline"][-1]["text"]


def test_return_recalls_drone(client):
    _seed(client)
    r = client.post("/api/drones/drone-case-x/command", json={"command": "return"})
    assert r.status_code == 200
    assert "case-x" not in client.app.state.runtime.runner.world.drones


def test_unknown_drone_404_and_bad_command_422(client):
    assert client.post("/api/drones/nope/command", json={"command": "speak"}).status_code == 404
    _seed(client)
    assert client.post("/api/drones/drone-case-x/command", json={"command": "explode"}).status_code == 422


def test_health_reports_modes(client):
    modes = client.get("/api/health").json()["modes"]
    assert modes["outreach"] == "mock"
    assert set(modes) == {"data_mode", "outreach", "feeds", "region", "db"}
