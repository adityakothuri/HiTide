"""Regional road evidence. Timestamp ambiguity remains explicit at the preview boundary."""

import asyncio
from dataclasses import replace
from typing import Any

from feeds.base import fetch_live_page
from feeds.intake import FeedRequest, RawEnvelope, split_response

ATX = FeedRequest(
    "atx_flood_closures", "atx_closures",
    "https://maps.austintexas.gov/gis/rest/PublicSafetySharedServices/SharedAtxFloodRoadClosure/MapServer/0/query",
    {"f": "geojson", "where": "1=1", "outFields": "*", "outSR": "4326"},
    {"state": "TX", "region": "ATXFloods participating jurisdictions"}, "features", 15,
)
SARIVER = FeedRequest(
    "sariver_crossings", "sariver_crossings",
    "https://api.bexarflood.org/api/sensors/GetAll", {},
    {"state": "TX", "counties": ["Bexar", "Wilson", "Karnes", "Goliad"]}, "array", 15,
)
TRANSTAR_DOCS = "https://traffic.houstontranstar.org/api/api_doc.aspx"
STATUSES = {1: "Closed", 2: "Open", 3: "Inactive", 4: "Caution"}


async def _collect(request: FeedRequest) -> list[RawEnvelope]:
    response = await fetch_live_page(request.product, request.url, request.params, request.timeout_s)
    rows = split_response(request, response)
    for row in rows:
        row.request_params.update(request.params)
    payload = response.get("data")
    if isinstance(payload, dict) and payload.get("error"):
        return [replace(rows[0], retrieval_status="failed", errors=("provider_error",))]
    if isinstance(payload, dict) and payload.get("exceededTransferLimit"):
        rows.append(replace(rows[0], raw_payload=None, source_record_id=None,
                            retrieval_status="failed", errors=("incomplete_response",)))
    return rows


def _transtar_marker(source: str) -> RawEnvelope:
    request = FeedRequest(source, source, TRANSTAR_DOCS, {}, {"state": "TX", "region": "Houston"}, "features")
    return split_response(request, {"source": "unavailable", "data": None,
                                   "errors": ("live_feed_access_required",)})[0]


async def collect_regional_roads() -> list[RawEnvelope]:
    atx, sariver = await asyncio.gather(_collect(ATX), _collect(SARIVER))
    return [*atx, *sariver,
            _transtar_marker("transtar_incidents"),
            _transtar_marker("transtar_lane_closures"),
            _transtar_marker("transtar_flood_risk")]


def preview_regional(raw: RawEnvelope) -> dict[str, Any] | None:
    """Temporary display interpretation. No UTC offset is invented for local sensor times."""
    if raw.retrieval_status != "success" or not isinstance(raw.raw_payload, dict):
        return None
    payload = raw.raw_payload
    if raw.source_id == "atx_flood_closures":
        props = payload.get("properties")
        if not isinstance(props, dict):
            return None
        return {"title": str(props.get("NAME") or props.get("ADDRESS") or "ATXFloods crossing"),
                "detail": f"Provider status: {props.get('STATUS', 'Unknown')}. {props.get('COMMENT_') or ''}",
                "time": None, "geometry": payload.get("geometry"), "evidence_type": "context",
                "timestamp_role": "unknown", "link": "https://www.atxfloods.com/",
                "time_reason": "provider_observation_time_missing"}
    if raw.source_id == "sariver_crossings":
        status = STATUSES.get(payload.get("statusTypeID"), "Unknown")
        return {"title": str(payload.get("title") or "Monitored crossing"),
                "detail": f"Provider status: {status}. Last update: {payload.get('lastUpdated') or 'unknown'} (timezone unspecified).",
                "time": None,
                "geometry": {"type": "Point", "coordinates": [payload.get("lng"), payload.get("lat")]},
                "evidence_type": "context", "timestamp_role": "unknown",
                "link": "https://sariverflood.org/", "time_reason": "timestamp_timezone_unknown"}
    return None
