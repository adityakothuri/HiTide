"""NWS active alerts for Kerrville, TX (api.weather.gov)."""

from __future__ import annotations

from typing import Any

from feeds.base import fetch_with_fallback
from feeds.intake import FeedRequest, RawEnvelope, collect_request

NWS_ALERTS_URL = "https://api.weather.gov/alerts/active"
KERRVILLE_POINT = "30.0474,-99.1403"
ALERTS_REQUEST = FeedRequest("nws_alerts", "nws_alerts", NWS_ALERTS_URL, {"point": KERRVILLE_POINT},
                             {"point_lat_lon": KERRVILLE_POINT}, "features")


async def collect_alerts(*, cache_only: bool = False) -> list[RawEnvelope]:
    return await collect_request(ALERTS_REQUEST, cache_only=cache_only)


def _simplify_alert(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties") or {}
    return {
        "id": props.get("id") or feature.get("id"),
        "event": props.get("event"),
        "severity": props.get("severity"),
        "headline": props.get("headline"),
        "onset": props.get("onset"),
        "expires": props.get("expires"),
        "polygon": feature.get("geometry"),
    }


def simplify_alerts(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    return [_simplify_alert(f) for f in data.get("features") or [] if isinstance(f, dict)]


async def active_alerts() -> dict[str, Any]:
    """Envelope from fetch_with_fallback plus `alerts`: simplified active alerts (may be empty)."""
    envelope = await fetch_with_fallback(ALERTS_REQUEST.product, ALERTS_REQUEST.url, ALERTS_REQUEST.params,
                                         shape=ALERTS_REQUEST.shape)
    return {**envelope, "alerts": simplify_alerts(envelope["data"])}
