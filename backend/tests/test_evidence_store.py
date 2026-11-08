from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from evidence.models import ObservationIn
from evidence.store import Store


def observation(**changes):
    return {"source_id": "local_reports", "source_record_id": "report-1", "kind": "report",
            "observed_at": "2026-11-07T15:00:00Z", "road_id": "crossing-a", "access": "closed",
            "raw": {"text": "Water across crossing"}, **changes}


def test_repeat_fetch_deduplicates_and_keeps_original_receipt_time(tmp_path):
    store = Store(tmp_path / "flood.sqlite3")
    first = store.add_observation(observation())
    repeated = store.add_observation(observation(ingested_at="2026-11-07T18:00:00Z", source_mode="cached"))
    assert repeated == first
    assert len(store.list_observations()) == 1
    store.close()


def test_revisions_preserve_history_and_replaying_old_revision_does_not_supersede(tmp_path):
    store = Store(tmp_path / "flood.sqlite3")
    old = store.add_observation(observation())
    new = store.add_observation(observation(access="open", raw={"text": "Water receded"}))
    assert new["supersedes_id"] == old["id"]
    assert store.add_observation(observation())["id"] == old["id"]
    assert store.list_observations() == [old, new]
    store.close()


def test_database_reopens_with_dataset_tasks_and_evidence(tmp_path):
    path = tmp_path / "flood.sqlite3"
    store = Store(path)
    item = store.add_observation(observation())
    store.set_dataset({"roads": [{"id": "crossing-a"}], "simulated": True})
    store.save_task({"id": "task-1", "status": "assigned"})
    store.close()
    reopened = Store(path)
    assert reopened.list_observations() == [item]
    assert reopened.get_dataset()["roads"][0]["id"] == "crossing-a"
    assert reopened.list_tasks()[0]["status"] == "assigned"
    assert reopened.health()["ok"] is True
    reopened.close()


def test_mission_write_is_atomic_on_failure():
    store = Store(":memory:")
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.add_observation(observation())
            store.save_task({"id": "task-1", "status": "completed"})
            raise RuntimeError("assessment failed")
    assert store.list_observations() == []
    assert store.list_tasks() == []
    assert store.health()["raw_record_count"] == 0
    store.close()


def test_poll_metadata_does_not_create_an_observation_revision():
    store = Store(":memory:")
    first = store.add_observation(observation(raw={"text": "water", "fetched_at": "2026-11-07T15:01:00Z"}))
    repeat = store.add_observation(observation(raw={"text": "water", "fetched_at": "2026-11-07T15:02:00Z"}))
    assert first["id"] == repeat["id"]
    store.close()


@pytest.mark.parametrize("changes", [
    {"observed_at": "2026-11-07T12:00:00"},
    {"geometry": {"type": "Point", "coordinates": [-99, 130]}},
    {"value": float("nan"), "unit": "ft"},
    {"value": 12},
    {"kind": "gauge", "access": "unknown", "value": None, "unit": "ft"},
    {"kind": "gauge", "access": "closed", "value": 12, "unit": "ft"},
    {"observed_at": (datetime.now(UTC) + timedelta(days=2)).isoformat()},
])
def test_invalid_evidence_is_rejected(changes):
    with pytest.raises(ValidationError):
        ObservationIn.model_validate(observation(**changes))


def test_source_failure_does_not_retimestamp_observations():
    store = Store(":memory:")
    item = store.add_observation(observation())
    store.record_ingestion("local_reports", "failed", "timeout")
    assert store.list_observations() == [item]
    source = next(s for s in store.list_sources() if s["id"] == "local_reports")
    assert source["status"] == "failed"
    assert source["last_attempt_at"]
    assert source["fetched_at"] is None
    store.close()


def test_cached_fetch_time_is_not_last_attempt_or_successful_live_fetch():
    store = Store(":memory:")
    store.record_ingestion("usgs_gage", "live", fetched_at="2026-11-07T14:00:00Z")
    store.record_ingestion("usgs_gage", "cached", fetched_at="2026-11-07T14:00:00Z")
    source = next(s for s in store.list_sources() if s["id"] == "usgs_gage")
    assert source["fetched_at"] == "2026-11-07T14:00:00Z"
    assert source["last_successful_fetch_at"] == "2026-11-07T14:00:00Z"
    assert source["last_attempt_at"] != source["fetched_at"]
    store.close()


def test_supersession_cannot_rewrite_other_source_lineage():
    store = Store(":memory:")
    item = store.add_observation(observation())
    with pytest.raises(ValueError, match="supersed"):
        store.add_observation(observation(source_id="another_source", supersedes_id=item["id"]))
    assert len(store.list_observations()) == 1
    store.close()
