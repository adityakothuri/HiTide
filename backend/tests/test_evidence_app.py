"""Full app lifecycle and persisted inspection against a real MongoDB replica set."""

import os
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient


def test_full_app_mongo_inspection_survives_restart(monkeypatch):
    uri = os.environ.get("MONGODB_TEST_URI")
    if not uri:
        pytest.skip("set MONGODB_TEST_URI for the full MongoDB app integration")
    name = f"hitide_test_{uuid.uuid4().hex}"
    monkeypatch.setenv("HITIDE_DB_BACKEND", "mongodb")
    monkeypatch.setenv("MONGODB_URI", uri)
    monkeypatch.setenv("MONGODB_DATABASE", name)
    monkeypatch.setenv("PHOTON_MODE", "mock")
    monkeypatch.setenv("EVIDENCE_POLL_SECONDS", "0")
    from app.main import app

    try:
        with TestClient(app) as client:
            assert client.get("/api/health").json()["ok"]
            health = client.get("/api/evidence/health").json()
            assert health["backend"] == "mongodb" and health["ok"]
            assert client.post("/api/evidence/demo", headers={"origin": "https://untrusted.invalid"}).status_code == 403
            state = client.post("/api/evidence/demo").json()
            task = state["tasks"][0]
            assert task["road_id"] == "demo-east"
            assert client.post(f"/api/evidence/tasks/{task['id']}/assign").status_code == 200
            response = client.post(f"/api/evidence/tasks/{task['id']}/complete", json={
                "outcome": "closed", "observed_at": datetime.now(UTC).isoformat(),
                "image_url": "/static/drone/flood_03.jpg", "water_depth_in": 14.5,
            })
            assert response.status_code == 200, response.text
            assert not response.json()["communities"][0]["optimistic_access"]
            observation_ids = [o["id"] for o in response.json()["observations"]]
        with TestClient(app) as client:
            state = client.get("/api/evidence/state").json()
            assert [o["id"] for o in state["observations"]] == observation_ids
            assert state["tasks"][0]["status"] == "completed"
            assert not state["communities"][0]["optimistic_access"]
            assert client.get("/api/evidence/nearby?lon=-99.13&lat=30.05&radius_m=2000").status_code == 200
    finally:
        assert name.startswith("hitide_test_") and len(name) == 48
        with MongoClient(uri, serverSelectionTimeoutMS=5000) as cleanup:
            cleanup.drop_database(name)
