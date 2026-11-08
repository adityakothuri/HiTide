"""Real MongoDB replica-set tests; each run uses and removes only its own UUID database."""

import os
import uuid

import pytest

from evidence.mongo_store import MongoStore


@pytest.fixture
def mongo():
    uri = os.environ.get("MONGODB_TEST_URI")
    if not uri:
        pytest.skip("set MONGODB_TEST_URI to run MongoDB integration tests")
    name = f"floodwatch_test_{uuid.uuid4().hex}"
    store = MongoStore(uri, name)
    try:
        yield store
    finally:
        assert name.startswith("floodwatch_test_") and len(name) == 48
        store.client.drop_database(name)
        store.close()


def observation(**changes):
    return {"source_id": "local_reports", "source_record_id": "report-1", "kind": "report",
            "observed_at": "2026-11-07T15:00:00Z", "road_id": "crossing-a", "access": "closed",
            "geometry": {"type": "Point", "coordinates": [-99.14, 30.047]},
            "raw": {"text": "Water across crossing"}, **changes}


def test_mongo_history_dedup_and_source_health(mongo):
    old = mongo.add_observation(observation())
    new = mongo.add_observation(observation(access="open", raw={"text": "reopened"}))
    assert new["supersedes_id"] == old["id"]
    assert mongo.add_observation(observation(source_mode="cached")) == old
    assert mongo.list_observations() == [old, new]
    mongo.record_ingestion("local_reports", "failed", "timeout")
    source = next(s for s in mongo.list_sources() if s["id"] == "local_reports")
    assert source["status"] == "failed"
    assert source["fetched_at"] is None
    assert source["last_attempt_at"]
    assert mongo.health()["ok"] is True


def test_mongo_atomic_mission_rolls_back(mongo):
    with pytest.raises(RuntimeError):
        with mongo.transaction():
            mongo.add_observation(observation())
            mongo.save_task({"id": "task-1", "status": "completed"})
            raise RuntimeError("assessment failed")
    assert mongo.list_observations() == []
    assert mongo.list_tasks() == []
    assert mongo.health()["raw_record_count"] == 0


def test_mongo_actual_2dsphere_queries_and_separate_road_storage(mongo):
    near = mongo.add_observation(observation())
    mongo.add_observation(observation(source_record_id="far", geometry={"type": "Point", "coordinates": [-97, 32]}))
    dataset = {"id": "test", "simulated": True, "communities": [], "destinations": [], "roads": [
        {"id": "crossing-a", "name": "Crossing A", "from_node": "a", "to_node": "b",
         "geometry": {"type": "LineString", "coordinates": [[-99.141, 30.047], [-99.139, 30.047]]}}]}
    mongo.set_dataset(dataset)
    assert mongo.get_dataset() == dataset
    assert "roads" not in mongo.db.settings.find_one({"_id": "dataset"})["body"]
    assert [o["id"] for o in mongo.nearby_observations(-99.14, 30.047, 100)] == [near["id"]]
    region = {"type": "Polygon", "coordinates": [[[-99.142, 30.046], [-99.138, 30.046],
              [-99.138, 30.048], [-99.142, 30.048], [-99.142, 30.046]]]}
    assert [r["id"] for r in mongo.intersecting_roads(region)] == ["crossing-a"]


def test_mongo_reopens_without_destroying_existing_history(mongo):
    item = mongo.add_observation(observation())
    second = MongoStore(os.environ["MONGODB_TEST_URI"], mongo.db.name)
    try:
        assert second.list_observations() == [item]
        assert second.health()["schema_version"] == 1
    finally:
        second.close()
