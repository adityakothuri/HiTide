"""Photon Spectrum adapter.

Spectrum Cloud's REST API (spectrum.photon.codes/openapi/json) has no
message-send endpoint; sending is only possible via the spectrum-ts SDK. This
adapter therefore targets a tiny local Node sidecar (not built here):

    POST {SIDECAR}/send  {"to", "body"}
    POST {SIDECAR}/poll  {"to", "question", "options"}

The sidecar holds SPECTRUM_PROJECT_ID / SPECTRUM_PROJECT_SECRET / SPECTRUM_LINE.
Functions return "sent" or "failed" and never raise. Phone numbers are never logged.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

TIMEOUT_S = 10.0
DEFAULT_SIDECAR_URL = "http://localhost:8787"

Status = Literal["sent", "failed"]


def _base_url() -> str:
    return os.environ.get("SPECTRUM_SIDECAR_URL", DEFAULT_SIDECAR_URL).rstrip("/")


async def _post(path: str, payload: dict, transport: httpx.AsyncBaseTransport | None) -> Status:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=transport) as client:
            headers = {"x-sidecar-key": os.environ.get("SIDECAR_KEY", "")}
            resp = await client.post(f"{_base_url()}{path}", json=payload, headers=headers)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error("spectrum sidecar %s returned HTTP %s", path, exc.response.status_code)
        return "failed"
    except httpx.HTTPError as exc:
        logger.error("spectrum sidecar %s error: %s", path, type(exc).__name__)
        return "failed"
    return "sent"


async def send_text(to: str, body: str, *, transport: httpx.AsyncBaseTransport | None = None) -> Status:
    return await _post("/send", {"to": to, "body": body}, transport)


async def send_poll(
    to: str,
    question: str,
    options: tuple[str, ...] | list[str],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Status:
    return await _post("/poll", {"to": to, "question": question, "options": list(options)}, transport)
