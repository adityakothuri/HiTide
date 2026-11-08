"""Regression coverage for the raw boundary, independent of normalization/DBs."""

from dataclasses import replace
from datetime import datetime

import httpx
import pytest
from feeds import base, collect_raw
from feeds.intake import collect_request, split_response
from feeds.nws import ALERTS_REQUEST
from feeds.usgs_flood_impacts import IMPACTS_REQUEST
from feeds.usgs_ogc import LATEST_REQUEST


def test_envelopes_preserve_provider_values_malformed_records_and_page_limits():
    raw = {"id": "feature-id", "properties": {"value": "-999999", "qualifier": None}}
    records = split_response(
        LATEST_REQUEST,
        {
            "source": "live",
            "fetched_at": "2020-01-01T00:00:00Z",
            "data": {"features": [raw, None], "links": [{"rel": "next"}]},
        },
    )
    good, malformed = records
    assert good.source_record_id == "feature-id"
    assert good.source_id == "usgs_gage"
    assert good.raw_payload == raw
    assert good.record_index == 0 and malformed.record_index == 1
    assert good.attempt_id == malformed.attempt_id
    assert good.provider_metadata["has_next_page"] is True
    assert malformed.raw_payload is None
    assert malformed.retrieval_status == "malformed"
    assert malformed.errors == ("unexpected_record_shape",)


def test_empty_failed_and_wrong_shapes_are_distinct():
    def summarize(payload, source="live"):
        (marker,) = split_response(ALERTS_REQUEST, {"source": source, "data": payload})
        return marker.retrieval_status, marker.raw_payload

    assert summarize({"features": []}) == ("empty", {"features": []})
    assert summarize({"features": None}) == ("malformed", {"features": None})
    assert summarize(None, "unavailable") == ("failed", None)
    (record,) = split_response(
        IMPACTS_REQUEST, {"source": "live", "data": [{"id": 0, "is_flooding": None}]}
    )
    assert record.source_record_id == "0"
    assert record.raw_payload["is_flooding"] is None


@pytest.mark.asyncio
async def test_live_fallback_scope_errors_and_private_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(base, "CACHE_DIR", tmp_path)
    request = replace(
        ALERTS_REQUEST,
        params={**ALERTS_REQUEST.params, "api_key": "private-test-value"},
    )

    async def success(*_):
        return {"features": [{"id": "a", "properties": {"id": "cap-id"}}]}, {
            "etag": "revision1"
        }

    monkeypatch.setattr(base, "_get_json", success)
    (live,) = await collect_request(request)
    assert live.provenance == "live" and live.source_record_id == "cap-id"
    assert "private-test-value" not in repr(live)
    assert "private-test-value" not in (tmp_path / "nws_alerts.json").read_text()

    async def failed(*_):
        raise httpx.ConnectError("secret in error URL")

    monkeypatch.setattr(base, "_get_json", failed)
    (cached,) = await collect_request(request)
    assert cached.provider_metadata["etag"] == "revision1"
    assert cached.provenance == "cached" and cached.retrieval_status == "success"
    assert cached.errors == ("ConnectError",)
    assert cached.payload_retrieved_at == live.payload_retrieved_at
    assert datetime.fromisoformat(cached.retrieved_at) >= datetime.fromisoformat(
        live.retrieved_at
    )
    assert cached.attempt_id != live.attempt_id
    (unavailable,) = await collect_request(replace(request, params={"point": "40,-90"}))
    assert unavailable.provenance == "unavailable"
    assert unavailable.errors == ("ConnectError", "cache_request_mismatch")
    assert unavailable.payload_retrieved_at is None


@pytest.mark.asyncio
async def test_legacy_fixture_scope_and_cache_only_no_http(monkeypatch, tmp_path):
    monkeypatch.setattr(base, "CACHE_DIR", tmp_path)
    (tmp_path / "nws_alerts.json").write_text('{"data":{"features":[]}}')

    async def unexpected(*_):
        pytest.fail("cache-only collection attempted a network call")

    monkeypatch.setattr(base, "_get_json", unexpected)
    envelopes = await collect_raw(cache_only=True)
    assert len(envelopes) == 4
    [alert] = [r for r in envelopes if r.source_id == "nws_alerts"]
    assert alert.retrieval_status == "empty" and alert.provenance == "cached"
    assert alert.payload_retrieved_at is None
    assert sum(r.retrieval_status == "failed" for r in envelopes) == 3
    (mismatch,) = await collect_request(
        replace(ALERTS_REQUEST, params={"point": "40,-90"}), cache_only=True
    )
    assert mismatch.errors == ("cache_request_mismatch",)


@pytest.mark.asyncio
async def test_wrong_shape_passed_through_without_poisoning_cache(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(base, "CACHE_DIR", tmp_path)
    source = {"@context": ["https://example.org", {"@version": 1.1}], "features": []}

    async def fetch(*_):
        return source, {}

    monkeypatch.setattr(base, "_get_json", fetch)
    (original,) = await collect_request(ALERTS_REQUEST)
    assert original.provider_metadata["jsonld_version"] == 1.1
    source = {"message": "something went wrong"}
    (malformed,) = await collect_request(ALERTS_REQUEST)
    assert malformed.retrieval_status == "malformed" and malformed.raw_payload == source
    (replay,) = await collect_request(ALERTS_REQUEST, cache_only=True)
    assert (
        replay.retrieval_status == "empty"
        and replay.raw_payload == original.raw_payload
    )
