"""Statewide public alert and gage queries. The geographic filters stay fixed across pages."""

from dataclasses import replace
from urllib.parse import parse_qs, urljoin, urlsplit

from feeds.base import fetch_live_page
from feeds.intake import FeedRequest, RawEnvelope, split_response
from feeds.nws import NWS_ALERTS_URL
from feeds.usgs_ogc import GAGE_HEIGHT_PARAM, OGC_BASE

TEXAS_ALERTS = FeedRequest(
    "nws_alerts",
    "nws_active_tx",
    NWS_ALERTS_URL,
    {"area": "TX"},
    {"state": "TX"},
    "features",
    10.0,
)
TEXAS_GAGES = FeedRequest(
    "usgs_gage",
    "usgs_latest_tx",
    f"{OGC_BASE}/collections/latest-continuous/items",
    {
        "state_code": "48",
        "parameter_code": GAGE_HEIGHT_PARAM,
        "time": "PT1H",
        "limit": 500,
        "f": "json",
    },
    {"state": "TX", "state_fips": "48"},
    "features",
    15.0,
)
# Bound latency if a provider repeats cursors or unexpectedly expands a query.
MAX_PAGES = 20


def _next_cursor(request: FeedRequest, payload: dict) -> str | None:
    pagination = payload.get("pagination")
    if pagination is not None and not isinstance(pagination, dict):
        raise ValueError("invalid_next_page")
    next_url = pagination.get("next") if isinstance(pagination, dict) else None
    links = payload.get("links", [])
    if not isinstance(links, list):
        raise TypeError("invalid_next_page")
    for link in links:
        if isinstance(link, dict) and link.get("rel") == "next":
            next_url = link.get("href")
            if not next_url:
                raise ValueError("invalid_next_page")
            break
    if next_url is None:
        return None
    if not isinstance(next_url, str):
        raise TypeError("invalid_next_page")
    try:
        target = urlsplit(urljoin(request.url, next_url))
        origin = urlsplit(request.url)
        if (target.scheme, target.netloc, target.path) != (
            origin.scheme,
            origin.netloc,
            origin.path,
        ):
            raise ValueError
        (cursor,) = parse_qs(target.query)["cursor"]
        if not cursor:
            raise ValueError
    except (ValueError, KeyError) as exc:
        raise ValueError("invalid_next_page") from exc
    # Only carry the opaque cursor to the original provider with the original filters.
    return cursor


async def _collect_pages(request: FeedRequest) -> list[RawEnvelope]:
    result: list[RawEnvelope] = []
    seen_cursors: set[str] = set()
    page_request = request
    for page in range(1, MAX_PAGES + 1):
        response = await fetch_live_page(
            request.product, request.url, page_request.params, request.timeout_s
        )
        envelopes = split_response(page_request, response)
        # Metadata is shared by all records in this page's attempt.
        envelopes[0].provider_metadata["page"] = page
        result.extend(envelopes)
        payload = response["data"]
        if (
            response["source"] != "live"
            or not isinstance(payload, dict)
            or not isinstance(payload.get("features"), list)
        ):
            break
        try:
            cursor = _next_cursor(request, payload)
            if cursor is None:
                break
            if cursor in seen_cursors:
                raise ValueError("repeated_page_cursor")
            if page == MAX_PAGES:
                raise ValueError("page_limit_reached")
        except (ValueError, TypeError) as exc:
            result.append(
                replace(
                    envelopes[0],
                    source_record_id=None,
                    record_index=None,
                    retrieval_status="failed",
                    raw_payload=None,
                    errors=(str(exc),),
                )
            )
            break
        seen_cursors.add(cursor)
        page_request = replace(request, params={**request.params, "cursor": cursor})
    return result


async def collect_texas_alerts() -> list[RawEnvelope]:
    return await _collect_pages(TEXAS_ALERTS)


async def collect_texas_gages() -> list[RawEnvelope]:
    return await _collect_pages(TEXAS_GAGES)
