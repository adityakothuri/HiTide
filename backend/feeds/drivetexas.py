"""DriveTexas WZDx work zones. Temporary process cache follows the five-minute poll policy."""

import asyncio
import json
import os
import threading
from datetime import UTC, datetime
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from feeds.base import USER_AGENT
from feeds.intake import FeedRequest, RawEnvelope, split_response

WZDX_REQUEST = FeedRequest(
    "drivetexas_work_zones", "drivetexas_wzdx",
    "https://api.drivetexas.org/api/conditions.wzdx.geojson",
    {}, {"state": "TX"}, "features", 20,
)
_lock = threading.Lock()
_response: dict | None = None
_next_poll = 0.0


def _fetch() -> dict:
    key = os.environ.get("DRIVETEXAS_API_KEY", "").strip()
    if not key:
        return {"source": "unavailable", "data": None, "errors": ("not_configured",)}
    # urllib does not emit the authenticated request URL to application HTTP logs.
    request = Request(WZDX_REQUEST.url + "?" + urlencode({"key": key}),
                      headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"})
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8").replace(key, "[redacted]"))
            metadata = {"http_status": response.status}
    except HTTPError as exc:
        return {"source": "unavailable", "data": None, "errors": (f"http_{exc.code}",)}
    except (URLError, TimeoutError, OSError, ValueError):
        return {"source": "unavailable", "data": None, "errors": ("retrieval_failed",)}
    return {"source": "live", "data": payload, "fetched_at": datetime.now(UTC).isoformat(),
            "provider_metadata": metadata}


def _snapshot() -> dict:
    global _response, _next_poll
    with _lock:
        if _response is None or monotonic() >= _next_poll:
            _response = _fetch()
            _next_poll = monotonic() + 300
        return _response


async def collect_work_zones() -> list[RawEnvelope]:
    response = await asyncio.to_thread(_snapshot)
    rows = split_response(WZDX_REQUEST, response)
    payload = response.get("data")
    info = payload.get("feed_info") if isinstance(payload, dict) else None
    if isinstance(info, dict):
        for row in rows:
            row.provider_metadata.update({
                "feed_updated_at": info.get("update_date"), "version": info.get("version"),
                "publisher": info.get("publisher"), "license": info.get("license"),
                "timestamp_role": "feed_publication",
            })
    return rows
