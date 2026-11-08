"""Outreach layer: texts, polls, voice calls and in-app TTS with safety guards."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from outreach.base import OutboundMessage, Outreach
from outreach.log import DEFAULT_LOG_PATH
from outreach.service import OutreachService

__all__ = ["OutboundMessage", "Outreach", "make_outreach"]


def make_outreach(
    emit: Callable[[str, dict], Awaitable[None]],
    is_moving: Callable[[str], bool],
    *,
    log_path: Path = DEFAULT_LOG_PATH,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Outreach:
    return OutreachService(emit, is_moving, log_path=log_path, transport=transport)
