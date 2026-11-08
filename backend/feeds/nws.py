"""NWS active alerts for Kerrville, TX (api.weather.gov)."""

from __future__ import annotations

from typing import Any

from feeds.base import fetch_with_fallback

NWS_ALERTS_URL = "https://api.weather.gov/alerts/active"
KERRVILLE_POINT = "30.0474,-99.1403"


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
    envelope = await fetch_with_fallback("nws_alerts", NWS_ALERTS_URL, {"point": KERRVILLE_POINT})
    return {**envelope, "alerts": simplify_alerts(envelope["data"])}
