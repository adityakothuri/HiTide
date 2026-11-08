"""Parse a free-text or poll reply from a driver or emergency contact. Danger always wins over ambiguity."""

from __future__ import annotations

import re
from typing import Literal

Reply = Literal["safe", "need_help"]

# English + Spanish (safety/messages.py asks Spanish speakers to reply AYUDA or BIEN).
_HELP = re.compile(r"\b(help|sos|emergency|trapped|stuck|ayuda|auxilio|atrapad[oa]|socorro)\b", re.I)
_NEGATED_SAFE = re.compile(r"\b(not|isn'?t|aren'?t|un)\s*(safe|ok|okay|fine)\b|\bunsafe\b|\bno\s+estoy\s+bien\b", re.I)
_SAFE = re.compile(r"\b(safe|ok|okay|fine|bien|a\s+salvo)\b", re.I)
# Spoken answer to the voice agent's "Are you okay?": a bare "no" means not okay, unless the turn reassures.
_REFUSAL = re.compile(r"^\W*(no|nope|nah)\b", re.I)
_REASSURED = re.compile(r"\b(fine|ok|okay|safe|good|alright|all\s+right|problem|worries)\b", re.I)


def parse_reply(text: str) -> Reply | None:
    if _HELP.search(text) or _NEGATED_SAFE.search(text):
        return "need_help"
    if _SAFE.search(text):
        return "safe"
    return None


def is_bare_refusal(text: str) -> bool:
    return bool(_REFUSAL.search(text)) and not _REASSURED.search(text)


def parse_spoken_reply(text: str) -> Reply | None:
    """A call-transcript turn. Texts ask for SAFE/HELP explicitly, so only the call treats a bare "no" as help."""
    if is_bare_refusal(text):
        return "need_help"
    return parse_reply(text)
