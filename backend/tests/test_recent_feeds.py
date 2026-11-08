from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import router
from feeds import recent
from feeds.intake import split_response
from feeds.usgs_ogc import LATEST_REQUEST


def gage(sample_time):
    [record] = split_response(LATEST_REQUEST, {"source": "live", "data": {
        "features": [{"properties": {"time": sample_time}}]}})
    return record


@pytest.mark.parametrize(("age_seconds", "reason"), [
    (900, None), (1800, None), (1801, "outside_window"), (-1, "future_time"),
])
def test_sample_age(age_seconds, reason):
    now = datetime.now(UTC)
    record = gage((now - timedelta(seconds=age_seconds)).isoformat())
    assert recent.exclusion_reason(record, now, 30) == reason
    assert recent.exclusion_reason(replace(record, provenance="cached"), now, 30) == "cached"


def test_recent_route_filters_and_reports_unknowns(monkeypatch):
    async def collect(request):
        if request == LATEST_REQUEST:
            return [gage(datetime.now(UTC).isoformat()), gage(None)]
        return split_response(request, {"source": "live", "data": {"features": []}})

    monkeypatch.setattr(recent, "collect_request", collect)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    assert client.get("/api/feeds/recent?max_age_minutes=31").status_code == 422
    result = client.get("/api/feeds/recent?scope=kerrville&max_age_minutes=15").json()
    assert result["max_age_minutes"] == 15
    assert result["sources"]["nws_alerts"]["excluded"] == {"empty": 1}
    assert result["sources"]["usgs_gage"]["excluded"] == {"unknown_time": 1}
    assert len(result["sources"]["usgs_gage"]["records"]) == 1

def test_default_scope_uses_shared_statewide_poll_and_exposes_partial_results(monkeypatch):
    calls = []

    async def collect(scope):
        calls.append(scope)
        now = datetime.now(UTC)
        fresh = gage((now - timedelta(minutes=20)).isoformat())
        failed_page = replace(fresh, raw_payload=None, retrieval_status="failed", errors=("page_limit_reached",))
        road = replace(fresh, source_id="nws_local_storm_reports", raw_payload={"properties": {
            "state": "TX", "typetext": "FLOOD", "remark": "Water over Main Street.",
            "valid": now.isoformat()}})
        return [fresh, failed_page, road]

    monkeypatch.setattr(recent, "collect_recent_inputs", collect)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        wide = client.get("/api/feeds/recent").json()
        narrow = client.get("/api/feeds/recent?max_age_minutes=15").json()
        assert client.get("/api/feeds/recent?scope=invalid").status_code == 422
    assert calls == ["texas"]
    assert wide["scope"] == "texas"
    assert wide["sources"]["usgs_gage"]["status"] == "partial"
    assert len(wide["sources"]["usgs_gage"]["records"]) == 1
    assert narrow["sources"]["usgs_gage"]["records"] == []
    assert len(narrow["sources"]["nws_local_storm_reports"]["records"]) == 1

def test_expanded_sources_preserve_unknown_time_context_and_access_failures(monkeypatch):
    from feeds.intake import FeedRequest
    from feeds.regional_roads import SARIVER

    async def collect(scope):
        [sensor] = split_response(SARIVER, {"source": "live", "data": [{
            "id": 1, "title": "Crossing", "statusTypeID": 1,
            "lat": 29.5, "lng": -98.4, "lastUpdated": "2026-11-07T22:30:00"}]})
        blocked = split_response(FeedRequest("transtar_incidents", "transtar", "", {}, {"state": "TX"}, "features"),
                                 {"source": "unavailable", "data": None, "errors": ("live_feed_access_required",)})[0]
        return [sensor, blocked]

    monkeypatch.setattr(recent, "collect_recent_inputs", collect)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        data = client.get("/api/feeds/recent").json()
    sensor = data["sources"]["sariver_crossings"]
    assert sensor["status"] == "complete"
    assert sensor["records"] == []
    assert sensor["context"][0]["preview"]["time"] is None
    assert sensor["context"][0]["preview"]["evidence_type"] == "context"
    assert data["sources"]["transtar_incidents"]["status"] == "unavailable"
    assert data["sources"]["transtar_incidents"]["errors"] == ["live_feed_access_required"]

def test_map_projection_does_not_mutate_raw_snapshot():
    from dataclasses import asdict
    from feeds.recent import map_response
    raw = asdict(gage("2026-11-07T22:00:00Z"))
    raw["raw_payload"]["properties"]["unneeded"] = "preserve"
    response = {"sources": {"usgs_gage": {"records": [raw], "context": []}}}
    compact = map_response(response)
    assert "unneeded" not in compact["sources"]["usgs_gage"]["records"][0]["raw_payload"]["properties"]
    assert raw["raw_payload"]["properties"]["unneeded"] == "preserve"
