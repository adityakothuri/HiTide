import pytest

from evidence.store import Store


@pytest.mark.asyncio
async def test_cached_observation_preserves_measurement_time_and_deduplicates(monkeypatch):
    from evidence import ingestion

    async def gauge():
        return {"source": "cached", "fetched_at": "2026-11-07T15:02:00Z",
                "monitoring_location_id": "USGS-08166200",
                "latest": {"time": "2026-11-07T15:00:00Z", "value_ft": 8.2},
                "series_24h": [{"time": "2026-11-07T15:00:00Z", "value_ft": 8.2}]}

    async def empty():
        return {"source": "live", "data": {}, "alerts": [], "impacts": []}

    monkeypatch.setattr(ingestion, "gage_height", gauge)
    monkeypatch.setattr(ingestion, "active_alerts", empty)
    monkeypatch.setattr(ingestion, "flood_impacts", empty)
    store = Store(":memory:")
    await ingestion.ingest_feeds(store)
    await ingestion.ingest_feeds(store)
    rows = store.list_observations()
    assert len(rows) == 1
    assert rows[0]["observed_at"] == "2026-11-07T15:00:00+00:00"
    assert rows[0]["source_mode"] == "cached"
    assert rows[0]["access"] == "unknown"
    assert rows[0]["road_id"] is None
    assert rows[0]["value"] == 8.2
    assert rows[0]["unit"] == "ft"
    store.close()


@pytest.mark.asyncio
async def test_legacy_gauge_fallback_reports_selected_reading_provenance(monkeypatch):
    from feeds import usgs_ogc

    async def fetch(name, *args, **kwargs):
        if name == "usgs_gage_latest":
            return {"source": "live", "fetched_at": "2026-11-07T16:00:00Z", "data": {"features": []}}
        return {"source": "cached", "fetched_at": "2026-11-07T15:00:00Z", "data": {"features": [
            {"properties": {"time": "2026-11-07T14:45:00Z", "value": "8.2"}}]}}

    monkeypatch.setattr(usgs_ogc, "fetch_with_fallback", fetch)
    envelope = await usgs_ogc.gage_height()
    assert envelope["latest"]["value_ft"] == 8.2
    assert envelope["source"] == "cached"
    assert envelope["fetched_at"] == "2026-11-07T15:00:00Z"
    assert envelope["latest_endpoint_source"] == "live"
    assert envelope["series_fetched_at"] == "2026-11-07T15:00:00Z"


@pytest.mark.asyncio
async def test_one_source_failure_does_not_discard_other_sources(monkeypatch):
    from evidence import ingestion

    async def broken():
        raise TimeoutError("provider timed out")

    async def alerts():
        return {"source": "live", "alerts": [{"id": "warning-1", "event": "Flash Flood Warning",
                "onset": "2026-11-07T15:00:00Z", "expires": "2026-11-07T18:00:00Z", "polygon": None}]}

    async def unavailable():
        return {"source": "unavailable", "impacts": []}

    monkeypatch.setattr(ingestion, "gage_height", broken)
    monkeypatch.setattr(ingestion, "active_alerts", alerts)
    monkeypatch.setattr(ingestion, "flood_impacts", unavailable)
    store = Store(":memory:")
    result = await ingestion.ingest_feeds(store)
    assert len(store.list_observations()) == 1
    assert store.list_observations()[0]["valid_until"] == "2026-11-07T18:00:00+00:00"
    sources = {s["id"]: s for s in store.list_sources()}
    assert sources["usgs_gage"]["status"] == "failed"
    assert sources["usgs_flood_impacts"]["status"] == "unavailable"
    assert sources["drivetexas"]["status"] == "not_configured"
    assert result["nws_alerts"]["observations"] == 1
    store.close()


@pytest.mark.asyncio
async def test_bad_record_is_flagged_without_losing_valid_gauge_reading(monkeypatch):
    from evidence import ingestion

    async def gauge():
        return {"source": "live", "latest": {"time": "2026-11-07T15:00:00Z", "value_ft": 8.2},
                "series_24h": [{"time": "bad-time", "value_ft": 10.0}]}

    async def empty():
        return {"source": "live", "alerts": [], "impacts": []}

    monkeypatch.setattr(ingestion, "gage_height", gauge)
    monkeypatch.setattr(ingestion, "active_alerts", empty)
    monkeypatch.setattr(ingestion, "flood_impacts", empty)
    store = Store(":memory:")
    result = await ingestion.ingest_feeds(store)
    assert len(store.list_observations()) == 1
    assert result["usgs_gage"]["rejected"] == 1
    assert next(s for s in store.list_sources() if s["id"] == "usgs_gage")["status"] == "partial"
    store.close()


@pytest.mark.asyncio
async def test_series_survives_latest_endpoint_outage_and_preserves_own_mode(monkeypatch):
    from evidence import ingestion

    async def gauge():
        return {"source": "unavailable", "series_source": "cached", "latest": None,
                "series_24h": [{"time": "2026-11-07T15:00:00Z", "value_ft": 8.2}]}

    async def empty():
        return {"source": "live", "alerts": [], "impacts": []}

    monkeypatch.setattr(ingestion, "gage_height", gauge)
    monkeypatch.setattr(ingestion, "active_alerts", empty)
    monkeypatch.setattr(ingestion, "flood_impacts", empty)
    store = Store(":memory:")
    result = await ingestion.ingest_feeds(store)
    assert store.list_observations()[0]["source_mode"] == "cached"
    assert result["usgs_gage"]["status"] == "partial"
    store.close()
