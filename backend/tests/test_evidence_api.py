"""Real SQLite + FastAPI tests for the complete verification feedback loop."""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from evidence.routes import router
from evidence.service import EvidenceService
from evidence.store import Store


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    app.state.evidence = EvidenceService(Store(tmp_path / "evidence.sqlite3"))
    app.include_router(router)
    with TestClient(app) as client:
        yield client
    app.state.evidence.store.close()


def task_from_demo(client):
    response = client.post("/api/evidence/demo")
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["dataset"]["simulated"]
    assert [t["road_id"] for t in state["tasks"]] == ["demo-east"]
    return state["tasks"][0]


def completion(outcome):
    return {"outcome": outcome, "observed_at": datetime.now(UTC).isoformat(), "image_url": "/static/drone/flood_03.jpg", "water_depth_in": 14.5}


def test_complete_loop_updates_access_and_does_not_repeat_completed_task(client):
    task = task_from_demo(client)
    assert client.post(f"/api/evidence/tasks/{task['id']}/assign").status_code == 200
    response = client.post(f"/api/evidence/tasks/{task['id']}/complete", json=completion("closed"))
    assert response.status_code == 200, response.text
    state = response.json()
    east = next(r for r in state["roads"] if r["id"] == "demo-east")
    assert east["access"] == "closed"
    community = state["communities"][0]
    assert not community["optimistic_access"] and not community["conservative_access"]
    assert state["tasks"][0]["status"] == "completed"
    again = client.get("/api/evidence/state").json()
    assert again["tasks"][0]["status"] == "completed"
    assert len(again["observations"]) == 7
    assert next(o for o in again["observations"] if o["kind"] == "drone")["raw"]["image_url"] == "/static/drone/flood_03.jpg"


def test_completion_requires_assignment_and_rejects_repeat(client):
    task = task_from_demo(client)
    endpoint = f"/api/evidence/tasks/{task['id']}/complete"
    assert client.post(endpoint, json=completion("closed")).status_code == 409
    client.post(f"/api/evidence/tasks/{task['id']}/assign")
    assert client.post(endpoint, json=completion("closed")).status_code == 200
    assert client.post(endpoint, json=completion("closed")).status_code == 409


def test_inconclusive_result_keeps_gap_and_can_be_reassigned(client):
    task = task_from_demo(client)
    client.post(f"/api/evidence/tasks/{task['id']}/assign")
    state = client.post(f"/api/evidence/tasks/{task['id']}/complete", json=completion("inconclusive")).json()
    assert state["tasks"][0]["status"] == "inconclusive"
    assert next(r for r in state["roads"] if r["id"] == "demo-east")["access"] == "unknown"
    assert client.post(f"/api/evidence/tasks/{task['id']}/assign").status_code == 200


def test_demo_replay_preserves_history_and_scopes_old_inspections(client):
    task = task_from_demo(client)
    client.post(f"/api/evidence/tasks/{task['id']}/assign")
    client.post(f"/api/evidence/tasks/{task['id']}/complete", json=completion("closed"))
    replayed = client.post("/api/evidence/demo").json()
    assert len(replayed["observations"]) == 6
    assert replayed["historical_observation_count"] == 13
    assert replayed["tasks"][0]["status"] == "queued"
    assert replayed["tasks"][0]["id"] != task["id"]
    assert replayed["communities"][0]["optimistic_access"]


def test_reports_cannot_elevate_trust_and_validate_times_roads(client):
    task_from_demo(client)
    report = {"road_id": "demo-east", "observed_at": datetime.now(UTC).isoformat(), "access": "open", "raw": {"description": "Looks clear"}}
    response = client.post("/api/evidence/reports", json=report)
    assert response.status_code == 200, response.text
    assert next(r for r in response.json()["roads"] if r["id"] == "demo-east")["access"] == "unknown"
    assert client.post("/api/evidence/reports", json={**report, "quality": "agency"}).status_code == 422
    assert client.post("/api/evidence/reports", json={**report, "observed_at": "2026-11-07T20:00:00"}).status_code == 422
    assert client.post("/api/evidence/reports", json={**report, "road_id": "not-a-road"}).status_code == 422


def test_completion_validation(client):
    task = task_from_demo(client)
    client.post(f"/api/evidence/tasks/{task['id']}/assign")
    endpoint = f"/api/evidence/tasks/{task['id']}/complete"
    assert client.post(endpoint, json={**completion("closed"), "water_depth_in": -1}).status_code == 422
    assert client.post(endpoint, json={**completion("closed"), "image_url": "javascript:alert(1)"}).status_code == 422


def test_completed_task_and_evidence_survive_database_restart(tmp_path):
    path = tmp_path / "persist.sqlite3"
    store = Store(path)
    service = EvidenceService(store)
    task = service.start_demo()["tasks"][0]
    service.assign(task["id"])
    service.complete(task["id"], completion("closed"))
    store.close()
    reopened = Store(path)
    state = EvidenceService(reopened).snapshot()
    assert state["tasks"][0]["status"] == "completed"
    assert not state["communities"][0]["optimistic_access"]
    assert reopened.diagnostics()["ok"]
    reopened.close()


def test_completion_is_atomic_when_task_save_fails(tmp_path, monkeypatch):
    store = Store(tmp_path / "atomic.sqlite3")
    service = EvidenceService(store)
    task = service.start_demo()["tasks"][0]
    service.assign(task["id"])
    count = len(store.list_observations())
    original_save = store.save_task

    def fail_completion(task):
        if task["status"] == "completed":
            raise RuntimeError("disk full")
        return original_save(task)

    monkeypatch.setattr(store, "save_task", fail_completion)
    with pytest.raises(RuntimeError, match="disk full"):
        service.complete(task["id"], completion("closed"))
    assert len(store.list_observations()) == count
    assert store.list_tasks()[0]["status"] == "assigned"
    store.close()


def test_configuration_validates_graph_nodes_and_recomputes_priorities(client):
    task_from_demo(client)
    config = {"communities": [{"id": "origin", "name": "Known origin", "node_id": "other"}], "destinations": [{"id": "destination", "name": "Known destination", "node_id": "safe-west"}]}
    response = client.post("/api/evidence/configuration", json=config)
    assert response.status_code == 200
    assert response.json()["communities"][0]["conservative_access"]
    assert not [t for t in response.json()["tasks"] if t["status"] == "queued"]
    config["destinations"][0]["node_id"] = "not-a-node"
    assert client.post("/api/evidence/configuration", json=config).status_code == 422


def test_geospatial_endpoints_validate_inputs_and_do_not_fake_sqlite_support(client):
    assert client.get("/api/evidence/nearby?lon=-99.14&lat=30.04").status_code == 501
    assert client.get("/api/evidence/nearby?lon=-199&lat=30.04").status_code == 422
    assert client.post("/api/evidence/intersections", json={"geometry": {"type": "Point", "coordinates": [-99.14, 30.04]}}).status_code == 501
    assert client.post("/api/evidence/intersections", json={"geometry": {"type": "Point", "coordinates": []}}).status_code == 422
