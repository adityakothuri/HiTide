"""HTTP for live observation: one retry with backoff, last-good disk cache, no secrets in logs or cache keys."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from feeds.base import USER_AGENT, _read_cache, _request_signature, _write_cache, fetch_live_page

log = logging.getLogger(__name__)
RETRY_BACKOFF_S = 1.5
CACHE_PREFIX = "live_"     # data/feeds_cache/live_*.json (gitignored): lets a captured live frame replay offline


@dataclass(frozen=True)
class Fetched:
    data: Any
    provenance: str            # live | cached | none
    error: str | None = None


async def fetch_json(name: str, url: str, params: dict | None = None, timeout_s: float = 10.0) -> Fetched:
    errors: tuple[str, ...] = ()
    for attempt in range(2):
        resp = await fetch_live_page(name, url, params, timeout_s)
        if resp["source"] == "live":
            _write_cache(CACHE_PREFIX + name, {"fetched_at": resp["fetched_at"], "data": resp["data"],
                                               "provider_metadata": resp["provider_metadata"],
                                               "request_signature": _request_signature(url, params)})
            return Fetched(resp["data"], "live")
        errors = tuple(resp["errors"])
        if attempt == 0:
            await asyncio.sleep(RETRY_BACKOFF_S)
    cached = _read_cache(CACHE_PREFIX + name, _request_signature(url, params), errors)
    if cached["source"] == "cached":
        return Fetched(cached["data"], "cached", ",".join(errors) or None)
    return Fetched(None, "none", ",".join(cached["errors"]) or "unavailable")


async def fetch_bytes(url: str, timeout_s: float = 20.0) -> bytes:
    """Raises httpx.HTTPError after one retry."""
    last: Exception | None = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=timeout_s, headers={"User-Agent": USER_AGENT},
                                         follow_redirects=False) as client:
                r = await client.get(url)
                r.raise_for_status()
                return r.content
        except httpx.HTTPError as exc:
            last = exc
            if attempt == 0:
                await asyncio.sleep(RETRY_BACKOFF_S)
    assert last is not None
    raise last


async def fetch_text(url: str, timeout_s: float = 15.0) -> str:
    return (await fetch_bytes(url, timeout_s)).decode("utf-8", errors="replace")
