"""Apply an inbound reply (text or poll vote) from a phone to the right open case.

Shared by the Stable sidecar route (POST /api/photon/inbound) and the Photon 2.0 WebSocket listener.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from outreach.allowlist import normalize_phone, resolve_phone
from outreach.replies import parse_reply

log = logging.getLogger("outreach.inbound")


def mask_phone(value: str) -> str:
    """Last two digits only, for logs."""
    return f"***{value[-2:]}" if len(value) > 4 else "***"


NO_MATCH: dict[str, Any] = {"ok": True, "matched": False}


async def handle_inbound(runtime: Any, sender: str, text: str) -> dict[str, Any]:
    """Match only open cases whose driver or emergency contact resolves to `sender`; newest case wins.
    No Kerrville case -> the per-user safety monitor (Hill Country residents and enrolled users), if it is running."""
    kind = parse_reply(text)
    if kind is None:
        return dict(NO_MATCH)
    want = normalize_phone(sender)
    drivers = {d.id: d for d in runtime.drivers}
    matches = []  # open cases where the sender is the driver or their emergency contact
    for case in runtime.runner.world.cases.values():
        d = drivers.get(case.driver_id)
        if d is None or case.state == "resolved":
            continue
        for raw, by in ((d.phone, "driver"), (d.emergency_contact.phone, "emergency_contact")):
            resolved = resolve_phone(raw)
            if resolved and normalize_phone(resolved) == want:
                matches.append((runtime.runner.world.case_opened_s.get(case.id, 0.0), case.id, by))
    if matches:
        _, case_id, by = max(matches)  # most recently opened case for this number
        await runtime.runner.reply(case_id, kind, by)
        log.info("inbound %s from %s applied to %s as %s", kind, mask_phone(sender), case_id, by)
        return {"ok": True, "matched": True, "case_id": case_id, "reply": kind}
    safety = getattr(runtime, "safety", None)
    hit = safety.find_by_phone(sender) if safety is not None else None
    if hit is None:
        log.info("inbound %s from %s: no open case", kind, mask_phone(sender))
        return dict(NO_MATCH)
    user, by = hit
    acts = await asyncio.to_thread(safety.reply, user.id, kind, by)
    await safety.dispatch_actions(user, acts)
    log.info("inbound %s from %s applied to safety user %s as %s", kind, mask_phone(sender), user.id, by)
    return {"ok": True, "matched": True, "user_id": user.id, "reply": kind}
