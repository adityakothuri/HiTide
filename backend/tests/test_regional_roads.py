"""Regional adapters preserve incomplete timing and access failures."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from feeds import regional_roads as regional
from feeds.intake import split_response

EXAMPLES = Path(__file__).resolve().parents[2] / "docs/examples/map-data"


@pytest.mark.asyncio
async def test_regional_collection_and_context_boundary(monkeypatch):
    async def fetch(name, url, params, timeout):
        if url == regional.ATX.url:
            assert params["outSR"] == "4326"
            return {"source": "live", "data": {"type": "FeatureCollection", "features": []}}
        return {"source": "live", "data": json.loads(
            (EXAMPLES / "sariver-crossing-excerpt.json").read_text())}
    monkeypatch.setattr(regional, "fetch_live_page", fetch)
    rows = await regional.collect_regional_roads()
    assert rows[0].retrieval_status == "empty"
    sensor = rows[1]
    assert sensor.source_record_id == "2123"
    preview = regional.preview_regional(sensor)
    assert preview["time"] is None
    assert preview["timestamp_role"] == "unknown"
    assert preview["evidence_type"] == "context"
    assert "Provider status: Open" in preview["detail"]
    assert preview["geometry"]["coordinates"] == [-98.4480590820313, 29.5086116790771]
    assert {r.source_id for r in rows[2:]} == {
        "transtar_incidents", "transtar_lane_closures", "transtar_flood_risk"}
    assert all(r.errors == ("live_feed_access_required",) for r in rows[2:])


@pytest.mark.asyncio
async def test_provider_error_is_a_failed_attempt(monkeypatch):
    async def fetch(*args):
        return {"source": "live", "data": {"error": {"message": "Provider error"}}}
    monkeypatch.setattr(regional, "fetch_live_page", fetch)
    [row] = await regional._collect(regional.ATX)
    assert row.retrieval_status == "failed"
    assert row.errors == ("provider_error",)


def test_atx_missing_observation_time_stays_unknown():
    payload = {"features": [{"id": 10, "properties": {"NAME": "Example crossing", "STATUS": "Closed"},
                             "geometry": {"type": "Point", "coordinates": [-97.7, 30.2]}}]}
    [row] = split_response(regional.ATX, {"source": "live", "data": payload})
    preview = regional.preview_regional(row)
    assert preview["title"] == "Example crossing"
    assert preview["time"] is None
    assert preview["time_reason"] == "provider_observation_time_missing"
    assert regional.preview_regional(replace(row, retrieval_status="failed")) is None
