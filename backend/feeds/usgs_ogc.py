"""USGS gage height for the Guadalupe River at Kerrville via the Water Data OGC API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from feeds.base import fetch_with_fallback
from feeds.intake import FeedRequest, RawEnvelope, collect_request

logger = logging.getLogger(__name__)

OGC_BASE = "https://api.waterdata.usgs.gov/ogcapi/v1"
MONITORING_LOCATION = "USGS-08166200"
GAGE_HEIGHT_PARAM = "00065"  # gage height, ft
SERIES_WINDOW = "PT24H"
SERIES_LIMIT = 1000  # 15-min or 5-min data over 24 h fits well under this

_BASE_PARAMS = {
    "monitoring_location_id": MONITORING_LOCATION,
    "parameter_code": GAGE_HEIGHT_PARAM,
    "f": "json",
}

_SCOPE = {"monitoring_location_id": MONITORING_LOCATION}
LATEST_REQUEST = FeedRequest("usgs_gage", "usgs_gage_latest", f"{OGC_BASE}/collections/latest-continuous/items",
                             _BASE_PARAMS, _SCOPE, "features")
SERIES_REQUEST = FeedRequest("usgs_gage", "usgs_gage_24h", f"{OGC_BASE}/collections/continuous/items",
                             {**_BASE_PARAMS, "time": SERIES_WINDOW, "limit": SERIES_LIMIT}, _SCOPE, "features", 10.0)


async def collect_gage(*, cache_only: bool = False) -> list[RawEnvelope]:
    latest, series = await asyncio.gather(
        collect_request(LATEST_REQUEST, cache_only=cache_only), collect_request(SERIES_REQUEST, cache_only=cache_only)
    )
    return latest + series


def _to_point(feature: dict[str, Any]) -> dict[str, Any] | None:
    props = feature.get("properties") or {}
    try:
        value = float(props["value"])  # API returns value as a string
    except (KeyError, TypeError, ValueError):
        logger.debug("skipping gage reading with bad value: %s", props.get("value"))
        return None
    return {"time": props.get("time"), "value_ft": value}


def _points(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    points = [_to_point(f) for f in data.get("features") or [] if isinstance(f, dict)]
    return sorted((p for p in points if p), key=lambda p: p["time"] or "")


async def gage_height() -> dict[str, Any]:
    """Latest gage height plus a 24 h series.

    Returns {"name", "source", "fetched_at", "monitoring_location_id",
    "latest": {"time", "value_ft"} | None, "series_24h": [...], "series_source"}.
    """
    latest_env, series_env = await asyncio.gather(
        fetch_with_fallback(LATEST_REQUEST.product, LATEST_REQUEST.url, LATEST_REQUEST.params,
                            shape=LATEST_REQUEST.shape),
        fetch_with_fallback(SERIES_REQUEST.product, SERIES_REQUEST.url, SERIES_REQUEST.params,
                            SERIES_REQUEST.timeout_s, shape=SERIES_REQUEST.shape),
    )
    latest_points = _points(latest_env["data"])
    series = _points(series_env["data"])
    latest = latest_points[-1] if latest_points else (series[-1] if series else None)
    selected_env = latest_env if latest_points else series_env
    return {
        "name": "usgs_gage",
        "source": selected_env["source"] if latest else "unavailable",
        "fetched_at": selected_env["fetched_at"],
        "latest_endpoint_source": latest_env["source"],
        "monitoring_location_id": MONITORING_LOCATION,
        "latest": latest,
        "series_24h": series,
        "series_source": series_env["source"],
        "series_fetched_at": series_env["fetched_at"],
    }
