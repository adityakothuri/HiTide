"""Who may receive a real send.

- Demo teammates: "env:DEMO_PHONE_X" resolves to that env var (always allowed; consented in person).
- Enrolled users: a "+E.164" number, only when OUTREACH_ALLOW_ENROLLED=1 and the user consented to flood alerts.
- Anything else (simulated "sim:<id>" users, fake numbers) never resolves: the send is logged as suppressed.
"""

from __future__ import annotations

import os
import re

_ENV_REF = re.compile(r"^env:(DEMO_PHONE_[A-Z0-9_]+)$")
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def enrolled_sends_allowed() -> bool:
    return os.environ.get("OUTREACH_ALLOW_ENROLLED", "0") == "1"


def resolve_phone(raw: str, enrolled: bool = False) -> str | None:
    """Resolve a phone reference to a dialable number, or None when it isn't allowlisted."""
    match = _ENV_REF.match(raw or "")
    if match:
        value = os.environ.get(match.group(1), "").strip()
        return value or None
    if enrolled and enrolled_sends_allowed() and _E164.match(raw or ""):
        return raw
    return None


def normalize_phone(value: str) -> str:
    """Comparable form for matching inbound senders: digits with a leading +, US 10-digit numbers get +1.
    Non-phone handles (an iMessage email) are lower-cased as is."""
    v = (value or "").strip()
    if "@" in v:
        return v.lower()
    digits = re.sub(r"\D", "", v)
    if not digits:
        return ""
    if len(digits) == 10:
        digits = "1" + digits
    return "+" + digits
