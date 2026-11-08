from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from feeds import drivetexas
from feeds.recent import exclusion_reason


@pytest.mark.asyncio
async def test_work_zone_poll_metadata_privacy_and_cooldown(monkeypatch):
    now = datetime.now(UTC)
    payload = {"type": "FeatureCollection", "feed_info": {"update_date": now.isoformat(), "version": "4.2"},
               "features": [{"id": "work-1", "properties": {
                   "start_date": (now - timedelta(days=1)).isoformat(),
                   "end_date": (now + timedelta(days=1)).isoformat()}}]}
    calls = []
    def fetch():
        calls.append(True)
        return {"source": "live", "data": payload}
    monkeypatch.setattr(drivetexas, "_fetch", fetch)
    monkeypatch.setattr(drivetexas, "_response", None)
    monkeypatch.setattr(drivetexas, "_next_poll", 0)
    rows = await drivetexas.collect_work_zones()
    await drivetexas.collect_work_zones()
    assert len(calls) == 1
    row = rows[0]
    assert row.request_params == {}
    assert row.provider_metadata["timestamp_role"] == "feed_publication"
    assert exclusion_reason(row, now, 15) is None
    assert exclusion_reason(row, now + timedelta(minutes=31), 30) == "outside_window"
    ended = replace(row, raw_payload={"properties": {
        "start_date": (now - timedelta(days=2)).isoformat(),
        "end_date": (now - timedelta(days=1)).isoformat()}})
    assert exclusion_reason(ended, now, 30) == "outside_validity"


def test_no_key_and_denied_access_have_safe_errors(monkeypatch):
    monkeypatch.delenv("DRIVETEXAS_API_KEY", raising=False)
    assert drivetexas._fetch()["errors"] == ("not_configured",)
    monkeypatch.setenv("DRIVETEXAS_API_KEY", "test-secret")
    def denied(*args, **kwargs):
        from urllib.error import HTTPError
        raise HTTPError("https://example.org?key=test-secret", 401, "secret", {}, None)
    monkeypatch.setattr(drivetexas, "urlopen", denied)
    result = drivetexas._fetch()
    assert result["errors"] == ("http_401",)
    assert "test-secret" not in repr(result)
