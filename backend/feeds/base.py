"""Public HTTP feeds and their temporary last-success disk caches."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Literal

import httpx
from app.config import DATA_DIR

logger = logging.getLogger(__name__)

USER_AGENT = "StateFarmFloodWatch-HackUTD/0.1"
CACHE_DIR = DATA_DIR / "feeds_cache"
Source = Literal["live", "cached", "unavailable"]
RecordShape = Literal["features", "array"]


def response_records(payload: Any, shape: RecordShape) -> list | None:
    if shape == "features":
        payload = payload.get("features") if isinstance(payload, dict) else None
    return payload if isinstance(payload, list) else None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _request_signature(url: str, params: dict | None) -> str:
    """Bind a cache to a request without recording credentials or a query string."""
    encoded = json.dumps([url, params or {}], sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


# Prior caches have no request signature. These are the only four requests
# the original fixed-scope collectors used to populate those files.
_LEGACY_SIGNATURES = {
    "nws_alerts": _request_signature(
        "https://api.weather.gov/alerts/active", {"point": "30.0474,-99.1403"}
    ),
    "usgs_flood_impacts": _request_signature(
        "https://api.waterdata.usgs.gov/rtfi-api/referencepoints/nwis/08166200", None
    ),
}
for _name, _collection, _extra in (
    ("usgs_gage_latest", "latest-continuous", {}),
    ("usgs_gage_24h", "continuous", {"time": "PT24H", "limit": 1000}),
):
    _LEGACY_SIGNATURES[_name] = _request_signature(
        f"https://api.waterdata.usgs.gov/ogcapi/v1/collections/{_collection}/items",
        {
            "monitoring_location_id": "USGS-08166200",
            "parameter_code": "00065",
            "f": "json",
            **_extra,
        },
    )


def _write_cache(name: str, payload: dict) -> None:
    tmp = None
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w", dir=CACHE_DIR, delete=False, encoding="utf-8"
        ) as stream:
            tmp = Path(stream.name)
            json.dump(payload, stream, indent=2)
        os.replace(tmp, CACHE_DIR / f"{name}.json")
    except OSError:
        logger.warning("feed %s: failed to write temporary cache", name)
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                logger.warning("feed %s: failed to remove temporary file", name)


def _read_cache(name: str, signature: str, errors: tuple[str, ...]) -> dict[str, Any]:
    try:
        cached = json.loads((CACHE_DIR / f"{name}.json").read_text(encoding="utf-8"))
        if not isinstance(cached, dict) or "data" not in cached:
            raise ValueError
        if cached.get("request_signature", _LEGACY_SIGNATURES.get(name)) == signature:
            return {
                "name": name,
                "source": "cached",
                "fetched_at": cached.get("fetched_at"),
                "data": cached["data"],
                "provider_metadata": cached.get("provider_metadata", {}),
                "errors": errors,
            }
        reason = "cache_request_mismatch"
    except FileNotFoundError:
        reason = "cache_missing"
    except (OSError, ValueError):
        reason = "cache_unreadable"
    return {
        "name": name,
        "source": "unavailable",
        "fetched_at": None,
        "data": None,
        "provider_metadata": {},
        "errors": (*errors, reason),
    }


async def _get_json(
    url: str, params: dict | None, timeout_s: float
) -> tuple[Any, dict]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json, application/json",
    }
    async with httpx.AsyncClient(
        timeout=timeout_s, headers=headers, follow_redirects=False
    ) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        metadata = {
            k: response.headers[k]
            for k in ("content-type", "etag", "last-modified", "date")
            if k in response.headers
        }
        metadata["http_status"] = response.status_code
        return response.json(), metadata


async def fetch_live_page(
    name: str, url: str, params: dict | None, timeout_s: float
) -> dict:
    """One public provider request. Failures are recorded without URLs or secrets."""
    try:
        data, metadata = await _get_json(url, params, timeout_s)
    except (httpx.HTTPError, ValueError) as exc:
        reason = (
            f"http_{exc.response.status_code}"
            if isinstance(exc, httpx.HTTPStatusError)
            else type(exc).__name__
        )
        logger.warning("feed %s: %s", name, reason)
        return {
            "name": name,
            "source": "unavailable",
            "fetched_at": None,
            "data": None,
            "provider_metadata": {},
            "errors": (reason,),
        }
    return {
        "name": name,
        "source": "live",
        "fetched_at": _now_iso(),
        "data": data,
        "provider_metadata": metadata,
        "errors": (),
    }


async def fetch_with_fallback(
    name: str,
    url: str,
    params: dict | None = None,
    timeout_s: float = 5.0,
    *,
    cache_only: bool = False,
    shape: RecordShape | None = None,
) -> dict:
    signature = _request_signature(url, params)
    if cache_only:
        return _read_cache(name, signature, ())
    response = await fetch_live_page(name, url, params, timeout_s)
    if response["source"] == "unavailable":
        return _read_cache(name, signature, response["errors"])
    data = response["data"]
    # Return anomalous JSON for quarantine, but retain the previous usable cache.
    if shape is None or response_records(data, shape) is not None:
        _write_cache(
            name,
            {
                "fetched_at": response["fetched_at"],
                "data": data,
                "provider_metadata": response["provider_metadata"],
                "request_signature": signature,
            },
        )
    return response
