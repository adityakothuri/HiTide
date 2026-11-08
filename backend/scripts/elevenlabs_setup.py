"""Create (or update) the Flood Watch ElevenLabs voice agent and attach the Photon SMS number over SIP.

Run: uv run python -m scripts.elevenlabs_setup
Reads ELEVENLABS_API_KEY, PHOTON2_SMS_NUMBER, PHOTON2_SIP_HOST, PHOTON2_SIP_USERNAME, PHOTON2_SIP_OUTBOUND_PASSWORD
from ../.env and writes ELEVENLABS_AGENT_ID and ELEVENLABS_PHONE_NUMBER_ID back. Safe to re-run: it patches the
existing agent and reuses an already-imported number. Never prints secrets.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import httpx
from dotenv import load_dotenv

from scripts.photon2_enroll import REPO_ROOT, upsert_env

API = "https://api.elevenlabs.io/v1/convai"
TIMEOUT_S = 20.0
log = logging.getLogger("elevenlabs_setup")

SYSTEM_PROMPT = """You are the State Farm Flood Watch voice assistant. You are calling {{driver_first_name}}, whose car \
appears to be stopped in floodwater on {{street}}. The water is about {{water_depth_in}} inches deep. It may be night \
and they may be scared or older. Be calm and warm.

Rules:
- Short sentences. One question at a time. Never talk over them. Wait for the answer.
- First goal: find out if they are safe or need help. Ask: "Are you safe, or do you need help?"
- If they say they are safe and out of the water: say "Good. Please stay away from {{street}} until the water drops." \
Then end the call.
- If they need help, or the water is rising, or they are unsure: say "Help is being sent. I have flagged responders \
with your location." Then give the guidance below. Do not hang up first.
- Guidance (Turn Around, Don't Drown): Do not try to drive or walk through the water. If water is below the doors, \
stay in the car with the seatbelt off and doors unlocked. If water is at the doors or rising, get out through a window \
and climb onto the roof or higher ground. Call 911 if you can. Stay on the line.
- If {{call_purpose}} is "family": you are calling a family member of {{driver_first_name}}, not the driver. Tell them \
{{driver_first_name}}'s car stopped in floodwater on {{street}} and responders are flagged. Ask if they have reached \
{{driver_first_name}}. If they say {{driver_first_name}} is safe, record safe. Keep it under 45 seconds.
- If someone calls in asking about a road, say you cannot see live road data on this line and advise: "If you cannot \
see the road surface, do not drive it. Turn around, don't drown."
- Never promise a rescue time. Never invent road conditions. If asked something you do not know, say so.
- When the person is safe, or has the guidance and says goodbye, call the end_call tool.
- Keep the whole call under 90 seconds unless they need help."""

FIRST_MESSAGE = "{{opening_line}}"  # set per call by the backend (dynamic variables need no override permission)

DRIVER_STATUS_DESC = (
    "Whether the caller is safe or needs help. Use need_help if they say they need help, are trapped, the water is "
    "rising or inside the car, or they are hurt or panicking. Use safe only if they clearly say they are safe and out "
    "of danger. Use unknown if they never answered or it is unclear."
)


def agent_body() -> dict[str, Any]:
    return {
        "name": "State Farm Flood Watch",
        "tags": ["hackutd", "floodwatch"],
        "conversation_config": {
            "agent": {
                "first_message": FIRST_MESSAGE,
                "language": "en",
                "dynamic_variables": {"dynamic_variable_placeholders": {
                    "driver_first_name": "there", "street": "your road", "water_depth_in": "unknown",
                    "call_purpose": "driver",
                    "opening_line": "Hi, this is State Farm Flood Watch. Are you safe, or do you need help?"}},
                "prompt": {
                    "prompt": SYSTEM_PROMPT,
                    "llm": "gemini-2.5-flash",
                    "temperature": 0.3,
                    "built_in_tools": {"end_call": {
                        "name": "end_call",
                        "description": "End the call once the caller is safe or has received the safety guidance and said goodbye.",
                        "params": {"system_tool_type": "end_call"},
                    },
                    # Unanswered calls hit voicemail: leave one short message and hang up, so the backend treats it
                    # as "no answer" and escalation continues (family, responders, drone).
                    "voicemail_detection": {
                        "name": "voicemail_detection",
                        "description": "Use when the call reaches voicemail or an answering machine.",
                        "params": {"system_tool_type": "voicemail_detection",
                                   "voicemail_message": "This is State Farm Flood Watch. Your car appears stopped in "
                                                        "floodwater on {{street}}. Responders have been flagged. If you "
                                                        "can, reply SAFE or HELP to our text."},
                    }},
                },
            },
            "tts": {"model_id": "eleven_flash_v2", "agent_output_audio_format": "ulaw_8000", "optimize_streaming_latency": 3},
            "turn": {"turn_eagerness": "normal", "turn_timeout": 7},
            "conversation": {"max_duration_seconds": 180},
        },
        "platform_settings": {
            "data_collection": {"driver_status": {
                "type": "string", "description": DRIVER_STATUS_DESC, "enum": ["safe", "need_help", "unknown"]}},
        },
    }


def phone_body(agent_id: str) -> dict[str, Any]:
    return {
        "phone_number": os.environ["PHOTON2_SMS_NUMBER"],
        "label": "Flood Watch (Photon 2.0 SIP)",
        "provider": "sip_trunk",
        "supports_inbound": True,
        "supports_outbound": True,
        "agent_id": agent_id,
        "outbound_trunk_config": {
            "address": os.environ.get("PHOTON2_SIP_HOST", "sip.photon.codes:5061"),
            "transport": "tls",
            "media_encryption": "allowed",
            "credentials": {"username": os.environ["PHOTON2_SIP_USERNAME"],
                            "password": os.environ["PHOTON2_SIP_OUTBOUND_PASSWORD"]},
        },
        "inbound_trunk_config": {"media_encryption": "allowed"},
    }


_SECRET_ENV = ("ELEVENLABS_API_KEY", "PHOTON2_SIP_OUTBOUND_PASSWORD", "PHOTON2_SIP_USERNAME", "PHOTON2_API_KEY")


def _redact(text: str) -> str:
    """Upstream error bodies can echo request fields; never print a credential."""
    for key in _SECRET_ENV:
        value = os.environ.get(key, "")
        if len(value) >= 4:
            text = text.replace(value, "[redacted]")
    return text


def _check(resp: httpx.Response, what: str) -> dict[str, Any]:
    if resp.status_code >= 400:
        log.error("%s failed: HTTP %s %s", what, resp.status_code, _redact(resp.text[:600]))
        resp.raise_for_status()
    return resp.json() if resp.content else {}


def ensure_agent(client: httpx.Client) -> str:
    existing = os.environ.get("ELEVENLABS_AGENT_ID", "").strip()
    if existing:
        _check(client.patch(f"{API}/agents/{existing}", json=agent_body()), "update agent")
        print(f"updated agent {existing}")
        return existing
    agent_id = _check(client.post(f"{API}/agents/create", json=agent_body()), "create agent")["agent_id"]
    print(f"created agent {agent_id}")
    return agent_id


def ensure_number(client: httpx.Client, agent_id: str) -> str:
    number = os.environ["PHOTON2_SMS_NUMBER"]
    listed = _check(client.get(f"{API}/phone-numbers"), "list numbers")
    rows = listed if isinstance(listed, list) else listed.get("phone_numbers", [])
    match = next((r for r in rows if r.get("phone_number") == number), None)
    if match:
        pid = match["phone_number_id"]
        _check(client.patch(f"{API}/phone-numbers/{pid}", json={"agent_id": agent_id}), "assign agent")
        print(f"number already imported ({pid}); agent assigned")
        return pid
    pid = _check(client.post(f"{API}/phone-numbers", json=phone_body(agent_id)), "import number")["phone_number_id"]
    print(f"imported {number} as {pid} with agent attached")
    return pid


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv(REPO_ROOT / ".env")
    missing = [k for k in ("ELEVENLABS_API_KEY", "PHOTON2_SMS_NUMBER", "PHOTON2_SIP_USERNAME",
                           "PHOTON2_SIP_OUTBOUND_PASSWORD") if not os.environ.get(k)]
    if missing:
        log.error("missing in .env: %s", ", ".join(missing))
        return 1
    headers = {"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}
    try:
        with httpx.Client(timeout=TIMEOUT_S, headers=headers) as client:
            agent_id = ensure_agent(client)
            upsert_env(REPO_ROOT / ".env", "ELEVENLABS_AGENT_ID", agent_id)
            phone_id = ensure_number(client, agent_id)
            upsert_env(REPO_ROOT / ".env", "ELEVENLABS_PHONE_NUMBER_ID", phone_id)
    except httpx.HTTPError as exc:
        log.error("setup stopped: %s", type(exc).__name__)
        return 1
    print("wrote ELEVENLABS_AGENT_ID and ELEVENLABS_PHONE_NUMBER_ID to .env")
    return 0


if __name__ == "__main__":
    sys.exit(main())
