import copy
from dataclasses import replace
from datetime import timedelta

import pytest

from evidence.demo_warning_parser import project_warning
from evidence.flood_monitor import DemoFloodMonitor
from scripts import demo_flood_monitor as demo


def test_replay_through_intake_and_acceptance():
    (raw,) = demo.example_records()
    accepted = project_warning(raw).observation
    assert accepted is not None
    assert accepted == project_warning(demo.example_records()[0]).observation
    monitor = DemoFloodMonitor()
    assert (
        monitor.evaluate([accepted], as_of=accepted.valid_from - timedelta(seconds=1))
        == []
    )
    (opened,) = monitor.evaluate([], as_of=accepted.valid_from)
    assert opened.state == "warning_active"
    assert opened.supporting_observation_ids == (accepted.observation_id,)
    assert monitor.evaluate([accepted, accepted], as_of=accepted.valid_from) == []
    (expired,) = monitor.evaluate([], as_of=accepted.valid_until)
    assert expired.state == "warning_expired"
    assert (expired.event_id, expired.supporting_observation_ids) == (
        opened.event_id,
        opened.supporting_observation_ids,
    )
    assert monitor.evaluate([accepted], as_of=accepted.valid_until) == []
    with pytest.raises(ValueError):
        monitor.evaluate([accepted], as_of=accepted.valid_from)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("status", "Test", "outside_demo_status"),
        ("messageType", "Cancel", "unsupported_message_type"),
        ("messageType", "Update", "unsupported_message_type"),
        ("event", "Flood Watch", "outside_demo_warning_type"),
        ("expires", "2026-11-08", "invalid_provider_time"),
        ("expires", "2020-01-01T00:00:00Z", "invalid_validity_interval"),
    ],
)
def test_unsupported_or_malformed_warning_has_reason(field, value, reason):
    (raw,) = demo.example_records()
    feature = copy.deepcopy(raw.raw_payload)
    feature["properties"][field] = value
    decision = project_warning(replace(raw, raw_payload=feature))
    assert decision.observation is None and decision.reason == reason


@pytest.mark.asyncio
async def test_live_mode_excludes_cached_fallback(monkeypatch):
    async def cached():
        return demo.example_records()

    monkeypatch.setattr(demo, "collect_texas_alerts", cached)
    result = await demo.run(live=True)
    assert result["transitions"] == []
    assert result["decision_counts"] == {"cached_fallback_excluded_from_live_demo": 1}
