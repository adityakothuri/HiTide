"""Shared types for the outreach layer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol

Recipient = Literal["driver", "parent", "emergency_contact"]
Channel = Literal["text", "poll", "voice", "tts_in_app"]


@dataclass(frozen=True)
class OutboundMessage:
    driver_id: str
    recipient: Recipient
    channel: Channel
    body: str
    phone: str  # raw from driver data: "env:DEMO_PHONE_A" or "+1830555xxxx"
    case_id: str | None = None
    poll_options: tuple[str, ...] = ()
    # Dynamic variables for the voice agent (e.g. driver_name); excluded from hash/eq.
    variables: Mapping[str, str] = field(default_factory=dict, hash=False, compare=False)


class Outreach(Protocol):
    async def send(self, msg: OutboundMessage) -> dict:
        """Return an OutreachEvent payload dict (api.schemas.OutreachEvent fields)."""
        ...
