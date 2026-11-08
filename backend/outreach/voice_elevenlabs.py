"""ElevenLabs Conversational AI outbound call over SIP trunk.

POST https://api.elevenlabs.io/v1/convai/sip-trunk/outbound-call
The trunk itself (sip.spectrum.photon.codes:5061 TLS) is configured in the
ElevenLabs dashboard. Never raises; never logs the phone number.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

TIMEOUT_S = 10.0
OUTBOUND_URL = "https://api.elevenlabs.io/v1/convai/sip-trunk/outbound-call"
_ENV_VARS = ("ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID", "ELEVENLABS_PHONE_NUMBER_ID")

Status = Literal["sent", "failed"]


def voice_configured() -> bool:
    return all(os.environ.get(name, "").strip() for name in _ENV_VARS)


def _request_body(to: str, first_message: str) -> dict:
    return {
        "agent_id": os.environ["ELEVENLABS_AGENT_ID"],
        "agent_phone_number_id": os.environ["ELEVENLABS_PHONE_NUMBER_ID"],
        "to_number": to,
        "conversation_initiation_client_data": {
            "conversation_config_override": {"agent": {"first_message": first_message}}
        },
    }


async def place_call(
    to: str, first_message: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> Status:
    if not voice_configured():
        logger.error("elevenlabs voice env missing")
        return "failed"
    headers = {"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=transport) as client:
            resp = await client.post(OUTBOUND_URL, json=_request_body(to, first_message), headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("elevenlabs outbound call HTTP %s", exc.response.status_code)
        return "failed"
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("elevenlabs outbound call error: %s", type(exc).__name__)
        return "failed"
    if not isinstance(data, dict) or not data.get("success", False):
        logger.error("elevenlabs outbound call rejected")
        return "failed"
    return "sent"
