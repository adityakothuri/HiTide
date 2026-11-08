"""Only consented teammate numbers (env:DEMO_PHONE_*) may receive real sends."""

from __future__ import annotations

import os
import re

_ENV_REF = re.compile(r"^env:(DEMO_PHONE_[A-Z0-9_]+)$")


def resolve_phone(raw: str) -> str | None:
    """Resolve "env:DEMO_PHONE_X" to its value; anything else is not allowlisted."""
    match = _ENV_REF.match(raw or "")
    if not match:
        return None
    value = os.environ.get(match.group(1), "").strip()
    return value or None
