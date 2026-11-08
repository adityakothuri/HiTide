"""Outreach service: guard, allowlist, dispatch, log, emit."""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from outreach import photon_spectrum, voice_elevenlabs
from outreach.allowlist import resolve_phone
from outreach.base import OutboundMessage
from outreach.log import DEFAULT_LOG_PATH, append_log
from sim.engine import now_iso

logger = logging.getLogger(__name__)

SAFETY_QUESTION = "Are you okay?"
SAFETY_OPTIONS = ("I'm safe", "I need help")
GUARDED_CHANNELS = frozenset({"text", "poll", "voice"})

Emit = Callable[[str, dict], Awaitable[None]]


def _is_blocked(msg: OutboundMessage, is_moving: Callable[[str], bool]) -> bool:
    return (
        msg.recipient == "driver"
        and msg.channel in GUARDED_CHANNELS
        and is_moving(msg.driver_id)
    )


def _photon_enabled() -> bool:
    return os.environ.get("PHOTON_MODE", "").strip().lower() == "photon"


class OutreachService:
    def __init__(
        self,
        emit: Emit,
        is_moving: Callable[[str], bool],
        log_path: Path = DEFAULT_LOG_PATH,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._emit = emit
        self._is_moving = is_moving
        self._log_path = log_path
        self._transport = transport

    async def send(self, msg: OutboundMessage) -> dict:
        channel, body, mode, status = await self._decide(msg)
        payload = {
            "id": uuid.uuid4().hex[:12],
            "ts": now_iso(),
            "driver_id": msg.driver_id,
            "recipient": msg.recipient,
            "channel": channel,
            "body": body,
            "mode": mode,
            "status": status,
            "case_id": msg.case_id,
        }
        await self._record(payload)
        return payload

    async def _decide(self, msg: OutboundMessage) -> tuple[str, str, str, str]:
        if _is_blocked(msg, self._is_moving):
            logger.warning("blocked %s to moving driver %s", msg.channel, msg.driver_id)
            return msg.channel, msg.body, "mock", "blocked"
        if msg.channel == "tts_in_app":
            return msg.channel, msg.body, "mock", "sent"
        phone = resolve_phone(msg.phone)
        if phone is None or not _photon_enabled():
            return msg.channel, msg.body, "mock", "sent"
        return await self._send_photon(msg, phone)

    async def _send_photon(self, msg: OutboundMessage, phone: str) -> tuple[str, str, str, str]:
        t = self._transport
        if msg.channel == "text":
            status = await photon_spectrum.send_text(phone, msg.body, transport=t)
            return "text", msg.body, "photon", status
        if msg.channel == "poll":
            options = msg.poll_options or SAFETY_OPTIONS
            status = await photon_spectrum.send_poll(phone, msg.body, options, transport=t)
            return "poll", msg.body, "photon", status
        return await self._send_voice(msg, phone)

    async def _send_voice(self, msg: OutboundMessage, phone: str) -> tuple[str, str, str, str]:
        if voice_elevenlabs.voice_configured():
            status = await voice_elevenlabs.place_call(phone, msg.body, transport=self._transport)
            return "voice", msg.body, "photon", status
        logger.warning("voice env missing; falling back to safety poll")
        body = f"[Voice unavailable, sent poll] {SAFETY_QUESTION} Reply: I'm safe / I need help. ({msg.body})"
        status = await photon_spectrum.send_poll(
            phone, SAFETY_QUESTION, SAFETY_OPTIONS, transport=self._transport
        )
        return "poll", body, "photon", status

    async def _record(self, payload: dict) -> None:
        append_log(payload, self._log_path)
        try:
            await self._emit("outreach", payload)
        except Exception:  # noqa: BLE001 - emit must never break the caller
            logger.exception("outreach emit failed")
