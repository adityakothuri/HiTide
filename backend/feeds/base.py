"""Shared HTTP fetch with on-disk cache fallback for live data feeds."""

from __future__ import annotations

import json
import os
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

USER_AGENT = "StateFarmFloodWatch-HackUTD/0.1"
CACHE_DIR = DATA_DIR / "feeds_cache"

Source = Literal["live", "cached", "unavailable"]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _cache_path(name: str) -> Path:
    return CACHE_DIR / f"{name}.json"


def _envelope(name: str, source: Source, fetched_at: str, data: Any) -> dict[str, Any]:
    return {"name": name, "source": source, "fetched_at": fetched_at, "data": data}


def _write_cache(name: str, fetched_at: str, data: Any) -> None:
    """Persist a live payload. Failure to cache never breaks the live response."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"fetched_at": fetched_at, "data": data}
        tmp = _cache_path(name).with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, _cache_path(name))
    except OSError:
        logger.exception("feed %s: failed to write cache", name)


def _read_cache(name: str) -> dict[str, Any]:
    """Return a cached envelope, or an 'unavailable' one if no usable cache exists."""
    path = _cache_path(name)
    try:
        cached = json.loads(path.read_text())
    except FileNotFoundError:
        logger.warning("feed %s: no cache at %s", name, path)
        return _envelope(name, "unavailable", _now_iso(), None)
    except (OSError, json.JSONDecodeError):
        logger.exception("feed %s: unreadable cache at %s", name, path)
        return _envelope(name, "unavailable", _now_iso(), None)
    if not isinstance(cached, dict) or "data" not in cached:
        logger.error("feed %s: malformed cache at %s", name, path)
        return _envelope(name, "unavailable", _now_iso(), None)
    return _envelope(name, "cached", cached.get("fetched_at") or _now_iso(), cached["data"])


async def _get_json(url: str, params: dict | None, timeout_s: float) -> Any:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/geo+json, application/json"}
    async with httpx.AsyncClient(timeout=timeout_s, headers=headers, follow_redirects=False) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


async def fetch_with_fallback(
    name: str, url: str, params: dict | None = None, timeout_s: float = 5.0
) -> dict:
    """Fetch JSON live; on any failure serve data/feeds_cache/{name}.json instead.

    Returns {"name", "source": "live"|"cached"|"unavailable", "fetched_at", "data"}.
    For cached data, fetched_at is when the cached payload was originally fetched.
    """
    try:
        data = await _get_json(url, params, timeout_s)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("feed %s: live fetch failed (%s: %s); using cache", name, type(exc).__name__, exc)
        return _read_cache(name)
    fetched_at = _now_iso()
    _write_cache(name, fetched_at, data)
    return _envelope(name, "live", fetched_at, data)
