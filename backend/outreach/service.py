"""Outreach service: guard, allowlist, dispatch, log, emit."""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx

from outreach import photon2, photon_spectrum, voice_elevenlabs
from outreach.allowlist import resolve_phone
from outreach.base import OutboundMessage
from outreach.live_users import live_provider, live_users
from outreach.log import DEFAULT_LOG_PATH, append_log
from outreach.mode import PhotonMode, photon_mode
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


def _effective_mode(msg: OutboundMessage) -> PhotonMode:
    """HITIDE_LIVE_USERS go live via HITIDE_LIVE_PROVIDER whatever PHOTON_MODE says; everyone else follows PHOTON_MODE."""
    if msg.driver_id in live_users():
        return live_provider()
    return photon_mode()


def _spectrum_configured() -> bool:
    return all(os.environ.get(k, "").strip() for k in ("SPECTRUM_PROJECT_ID", "SPECTRUM_PROJECT_SECRET"))


@dataclass(frozen=True)
class _Result:
    channel: str
    body: str
    mode: str
    status: str
    provider: str | None = None
    call_id: str | None = None


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
        res = await self._decide(msg)
        payload = {
            "id": uuid.uuid4().hex[:12],
            "ts": now_iso(),
            "driver_id": msg.driver_id,
            "recipient": msg.recipient,
            "channel": res.channel,
            "body": res.body,
            "mode": res.mode,
            "status": res.status,
            "case_id": msg.case_id,
        }
        if res.provider is not None:
            payload["provider"] = res.provider
        if res.call_id is not None:
            payload["call_id"] = res.call_id
        await self._record(payload)
        return payload

    async def _decide(self, msg: OutboundMessage) -> _Result:
        if _is_blocked(msg, self._is_moving):
            logger.warning("blocked %s to moving driver %s", msg.channel, msg.driver_id)
            return _Result(msg.channel, msg.body, "mock", "blocked")
        if msg.channel == "tts_in_app":
            return _Result(msg.channel, msg.body, "mock", "sent")
        mode = _effective_mode(msg)
        if mode == "mock":
            return _Result(msg.channel, msg.body, "mock", "sent")
        phone = resolve_phone(msg.phone, enrolled=msg.enrolled)
        if phone is None:  # live mode, but this number isn't allowlisted: say so, never a fake "sent"
            return _Result(msg.channel, msg.body, "mock", "suppressed")
        logger.info("live %s to %s via %s", msg.channel, msg.driver_id, mode)
        return await self._send_live(msg, phone, mode)

    async def _send_live(self, msg: OutboundMessage, phone: str, mode: str) -> _Result:
        if msg.channel == "text":
            status, provider = await self._text(phone, msg.body, mode)
            return _Result("text", msg.body, "photon", status, provider)
        if msg.channel == "poll":
            options = msg.poll_options or SAFETY_OPTIONS
            status, provider = await self._poll(phone, msg.body, options, mode)
            return _Result("poll", msg.body, "photon", status, provider)
        return await self._send_voice(msg, phone, mode)

    async def _text(self, phone: str, body: str, mode: str) -> tuple[str, str]:
        t = self._transport
        if mode == "photon2":
            status = await photon2.send_text(phone, body, transport=t)
            if status == "sent" or not _spectrum_configured():
                return status, "photon2"
            logger.warning("photon2 text failed; retrying once via stable")
        return await photon_spectrum.send_text(phone, body, transport=t), "stable"

    async def _poll(
        self, phone: str, question: str, options: Sequence[str], mode: str
    ) -> tuple[str, str]:
        t = self._transport
        if mode == "photon2":
            status = await photon2.send_poll(phone, question, options, transport=t)
            if status == "sent" or not _spectrum_configured():
                return status, "photon2"
            logger.warning("photon2 poll failed; retrying once via stable")
        return await photon_spectrum.send_poll(phone, question, options, transport=t), "stable"

    async def _place_call(self, msg: OutboundMessage, phone: str) -> tuple[str, str | None]:
        try:
            result = await voice_elevenlabs.place_call(
                phone, msg.body, msg.variables, transport=self._transport
            )
        except Exception:  # noqa: BLE001 - a broken voice adapter must not break the caller
            logger.exception("voice call raised")
            return "failed", None
        return result.status, result.conversation_id

    async def _send_voice(self, msg: OutboundMessage, phone: str, mode: str) -> _Result:
        if voice_elevenlabs.voice_configured():
            status, call_id = await self._place_call(msg, phone)
            if status == "sent":
                return _Result("voice", msg.body, "photon", status, call_id=call_id)
            logger.warning("voice call failed; falling back to safety poll")
        else:
            logger.warning("voice env missing; falling back to safety poll")
        body = f"[Voice unavailable, sent poll] {SAFETY_QUESTION} Reply: I'm safe / I need help. ({msg.body})"
        status, provider = await self._poll(phone, SAFETY_QUESTION, SAFETY_OPTIONS, mode)
        return _Result("poll", body, "photon", status, provider)

    async def _record(self, payload: dict) -> None:
        append_log(payload, self._log_path)
        try:
            await self._emit("outreach", payload)
        except Exception:  # noqa: BLE001 - emit must never break the caller
            logger.exception("outreach emit failed")
