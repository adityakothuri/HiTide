"""Parse a free-text or poll reply from a driver or emergency contact. Danger always wins over ambiguity."""

from __future__ import annotations

import re
from typing import Literal

Reply = Literal["safe", "need_help"]

# English + Spanish (safety/messages.py asks Spanish speakers to reply AYUDA or BIEN).
_HELP = re.compile(r"\b(help|sos|emergency|trapped|stuck|ayuda|auxilio|atrapad[oa]|socorro)\b", re.I)
_NEGATED_SAFE = re.compile(r"\b(not|isn'?t|aren'?t|un)\s*(safe|ok|okay|fine)\b|\bunsafe\b|\bno\s+estoy\s+bien\b", re.I)
_SAFE = re.compile(r"\b(safe|ok|okay|fine|bien|a\s+salvo)\b", re.I)


def parse_reply(text: str) -> Reply | None:
    if _HELP.search(text) or _NEGATED_SAFE.search(text):
        return "need_help"
    if _SAFE.search(text):
        return "safe"
    return None
