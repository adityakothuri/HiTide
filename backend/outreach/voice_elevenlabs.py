"""ElevenLabs Conversational AI outbound call over SIP trunk.

POST https://api.elevenlabs.io/v1/convai/sip-trunk/outbound-call -> {success, message, conversation_id, sip_call_id}
GET  https://api.elevenlabs.io/v1/convai/conversations/{id} -> {status, transcript, analysis, ...}
The trunk itself (sip.spectrum.photon.codes:5061 TLS) is configured in the
ElevenLabs dashboard. Never raises; never logs the phone number.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

TIMEOUT_S = 45.0  # outbound-call returns only once the SIP call connects (observed 10-20 s)
OUTBOUND_URL = "https://api.elevenlabs.io/v1/convai/sip-trunk/outbound-call"
CONVERSATION_URL = "https://api.elevenlabs.io/v1/convai/conversations/{conversation_id}"
_ENV_VARS = ("ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID", "ELEVENLABS_PHONE_NUMBER_ID")

Status = Literal["sent", "failed"]


@dataclass(frozen=True)
class CallResult:
    status: Status
    conversation_id: str | None


_FAILED = CallResult("failed", None)


def voice_configured() -> bool:
    return all(os.environ.get(name, "").strip() for name in _ENV_VARS)


def _request_body(to: str, first_message: str, variables: Mapping[str, str] | None) -> dict[str, Any]:
    # The agent's first message is "{{opening_line}}". ElevenLabs rejects first_message overrides on SIP calls,
    # but dynamic variables are always allowed, so the opening travels as a variable.
    client_data: dict[str, Any] = {"dynamic_variables": {**dict(variables or {}), "opening_line": first_message}}
    return {
        "agent_id": os.environ["ELEVENLABS_AGENT_ID"],
        "agent_phone_number_id": os.environ["ELEVENLABS_PHONE_NUMBER_ID"],
        "to_number": to,
        "conversation_initiation_client_data": client_data,
    }


async def place_call(
    to: str,
    first_message: str,
    variables: Mapping[str, str] | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> CallResult:
    if not voice_configured():
        logger.error("elevenlabs voice env missing")
        return _FAILED
    headers = {"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=transport) as client:
            resp = await client.post(OUTBOUND_URL, json=_request_body(to, first_message, variables), headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("elevenlabs outbound call HTTP %s", exc.response.status_code)
        return _FAILED
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("elevenlabs outbound call error: %s", type(exc).__name__)
        return _FAILED
    if not isinstance(data, dict) or not data.get("success", False):
        logger.error("elevenlabs outbound call rejected")
        return _FAILED
    conversation_id = data.get("conversation_id")
    return CallResult("sent", conversation_id if isinstance(conversation_id, str) else None)


async def get_conversation(
    conversation_id: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> dict[str, Any] | None:
    """Fetch a conversation (status, transcript, analysis). None on any failure."""
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        logger.error("elevenlabs api key missing")
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=transport) as client:
            resp = await client.get(CONVERSATION_URL.format(conversation_id=conversation_id),
                                    headers={"xi-api-key": key})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("elevenlabs get conversation HTTP %s", exc.response.status_code)
        return None
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("elevenlabs get conversation error: %s", type(exc).__name__)
        return None
    return data if isinstance(data, dict) else None
