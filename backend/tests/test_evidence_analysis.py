from datetime import UTC, datetime, timedelta

from evidence.analysis import analyze
from evidence.demo import demo_dataset, demo_observations

NOW = datetime(2026, 11, 7, 22, tzinfo=UTC)


def observations():
    return [{**o, "id": f"obs-{i}", "ingested_at": NOW.isoformat()} for i, o in enumerate(demo_observations(NOW))]


def test_last_exit_prioritized_over_stale_road_with_alternative():
    result = analyze(demo_dataset(), observations(), NOW)
    assert [c["road_id"] for c in result["candidates"]] == ["demo-east"]
    c = result["communities"][0]
    assert c["optimistic_access"] and not c["conservative_access"]
    assert c["remaining_exits"] == 1


def test_missing_evidence_is_unknown_and_gauge_never_sets_road_depth():
    result = analyze(demo_dataset(), [], NOW)
    assert all(r["access"] == "unknown" and r["freshness"] == "missing" for r in result["roads"])
    obs = observations()
    obs[4]["road_id"] = "demo-east"
    result = analyze(demo_dataset(), obs, NOW)
    east = next(r for r in result["roads"] if r["id"] == "demo-east")
    assert east["access"] == "unknown"
    assert "obs-4" not in east["evidence_ids"]


def test_fresh_drone_closure_removes_last_exit():
    obs = observations() + [{"id": "drone", "source_id": "drone", "source_record_id": "mission1", "kind": "drone", "road_id": "demo-east", "access": "closed", "quality": "operator", "observed_at": NOW.isoformat(), "ingested_at": NOW.isoformat()}]
    result = analyze(demo_dataset(), obs, NOW)
    assert not result["communities"][0]["optimistic_access"]
    assert not result["communities"][0]["conservative_access"]
    assert not result["candidates"]


def test_drone_open_cannot_silently_reopen_agency_closure():
    obs = observations() + [{"id": "drone", "source_id": "drone", "source_record_id": "mission1", "kind": "drone", "road_id": "demo-west", "access": "open", "quality": "operator", "observed_at": NOW.isoformat(), "ingested_at": NOW.isoformat()}]
    west = analyze(demo_dataset(), obs, NOW)["roads"][0]
    assert west["access"] == "closed" and west["agreement"] == "conflicting"


def test_explicitly_expired_agency_closure_does_not_remain_effective():
    obs = observations()
    obs[0]["valid_until"] = (NOW - timedelta(seconds=1)).isoformat()
    west = analyze(demo_dataset(), obs, NOW)["roads"][0]
    assert west["access"] == "unknown" and west["freshness"] == "stale"


def test_community_report_open_is_not_confirmed_access():
    obs = observations()
    obs[1].update(observed_at=NOW.isoformat(), quality="unverified")
    result = analyze(demo_dataset(), obs, NOW)
    assert result["roads"][1]["access"] == "unknown"
    assert not result["communities"][0]["conservative_access"]


def test_roads_respect_direction_and_physical_crossing_group():
    dataset = {"roads": [{"id": "out", "physical_id": "bridge", "name": "Bridge", "from_node": "a", "to_node": "b"}, {"id": "in", "physical_id": "bridge", "name": "Bridge", "from_node": "b", "to_node": "a"}], "communities": [{"id": "a", "name": "A", "node_id": "a"}], "destinations": [{"node_id": "b"}]}
    result = analyze(dataset, [], NOW)
    assert len(result["candidates"]) == 1
    obs = [{"id": "closure", "source_id": "agency", "source_record_id": "1", "kind": "closure", "road_id": "in", "observed_at": NOW.isoformat(), "access": "closed", "quality": "agency"}]
    result = analyze(dataset, obs, NOW)
    assert all(r["access"] == "closed" for r in result["roads"])
    assert not result["communities"][0]["optimistic_access"]


def test_delayed_old_measurement_does_not_replace_newer_source_measurement():
    obs = observations()
    obs += [{**obs[0], "id": "later", "source_record_id": "later", "observed_at": NOW.isoformat(), "access": "open"}, {**obs[0], "id": "delayed", "source_record_id": "old", "ingested_at": (NOW + timedelta(seconds=1)).isoformat()}]
    west = analyze(demo_dataset(), obs, NOW)["roads"][0]
    assert west["access"] == "open"


def test_no_origins_means_no_unsupported_inspection_priorities():
    dataset = demo_dataset()
    dataset["communities"] = []
    result = analyze(dataset, [], NOW)
    assert result["roads"]
    assert not result["candidates"]


def test_timestamp_order_is_chronological_across_offsets():
    obs = observations()
    obs[0]["observed_at"] = "2026-11-07T16:00:00-06:00"  # 22:00 UTC
    obs[0]["access"] = "open"
    obs.append({**obs[0], "id": "earlier", "source_record_id": "earlier", "observed_at": "2026-11-07T21:59:00Z", "access": "closed"})
    assert analyze(demo_dataset(), obs, NOW)["roads"][0]["access"] == "open"


def test_warning_polygon_adds_context_without_fabricating_road_closure():
    result = analyze(demo_dataset(), observations(), NOW)
    east = result["roads"][1]
    assert "obs-5" in east["context_ids"]
    assert east["access"] == "unknown"
    assert "obs-5" in east["evidence_ids"]


def test_dead_end_street_is_not_counted_as_a_remaining_exit():
    dataset = demo_dataset()
    dataset["roads"].append({"id": "dead-end", "name": "Dead end", "from_node": "neighborhood", "to_node": "dead-end", "bidirectional": True})
    result = analyze(dataset, observations(), NOW)
    assert result["communities"][0]["remaining_exits"] == 1


def test_new_same_agency_report_supersedes_reverse_direction_closure():
    dataset = {"roads": [{"id": "out", "physical_id": "bridge", "name": "Bridge", "from_node": "a", "to_node": "b"}, {"id": "in", "physical_id": "bridge", "name": "Bridge", "from_node": "b", "to_node": "a"}], "communities": [{"id": "a", "name": "A", "node_id": "a"}], "destinations": [{"node_id": "b"}]}
    obs = [{"id": "closure", "source_id": "agency", "source_record_id": "1", "kind": "closure", "road_id": "in", "observed_at": (NOW - timedelta(minutes=1)).isoformat(), "access": "closed", "quality": "agency"},
           {"id": "reopened", "source_id": "agency", "source_record_id": "2", "kind": "closure", "road_id": "out", "observed_at": NOW.isoformat(), "access": "open", "quality": "agency"}]
    result = analyze(dataset, obs, NOW)
    assert all(r["access"] == "open" and r["agreement"] == "consistent" for r in result["roads"])
