"""The phone app's "Call the HiTide assistant" line (inbound to the team's ElevenLabs + Photon agent).

When the person taps the button, the backend writes their situation and directions into the agent's default dynamic
variables, returns the assistant's number for the phone to dial, then watches the agent's conversations. When that
call ends, the transcript is classified (outreach.call_summary) and fed to the ladder like any call result: a
"need help" flags responders on the ops dashboard. Nothing here ever contacts 911.

The agent's defaults are global, so the line serves ONE session at a time: a new tap (any user) replaces the previous
session, and the defaults are reset to neutral text when a session ends, so a later caller never hears someone
else's name or street. Inbound calls carry no user id, so a session claims the first finished inbound conversation
that started after the tap, and each conversation is claimed at most once (demo-grade attribution; see docs).

Live only with HITIDE_ASSISTANT_LIVE=1 and the ELEVENLABS_* keys; otherwise a simulated entry is recorded.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any, Awaitable, Callable, Final, Mapping

from outreach import voice_elevenlabs
from outreach.call_summary import classify_call
from safety.directions import Directions
from safety.messages import ADVICE, first_name

log = logging.getLogger("safety.assistant")

LIVE_ENV: Final = "HITIDE_ASSISTANT_LIVE"
NUMBER_ENV: Final = "HITIDE_ASSISTANT_NUMBER"
WATCH_POLL_S: Final = 4.0
WATCH_MAX_S: Final = 15 * 60       # the person may take a while to dial and talk
START_SLACK_S: Final = 10.0        # a call that started just before the tap still counts (clock skew)
COOLDOWN_S: Final = 20.0           # repeat taps within this window reuse the prepared line (no new PATCH)
TRANSCRIPT_RETRIES: Final = 3      # a "done" row can appear before its transcript is ready
FINISHED: Final = ("done", "failed")
E164: Final = re.compile(r"^\+[1-9]\d{7,14}$")

# What a caller hears when no session is active (also written when a session ends).
NEUTRAL: Final[Mapping[str, str]] = {
    "driver_first_name": "there", "street": "your area", "water_depth_in": "unknown",
    "situation": "you may be near flooding", "advice": "Avoid low-water crossings. Never drive through water.",
    "directions": "Move to higher ground if water is rising near you, and stay away from flooded roads.",
    "call_purpose": "assistant",
}


def live_enabled() -> bool:
    flag = os.environ.get(LIVE_ENV, "").strip().lower() in ("1", "true", "yes", "on")
    return flag and voice_elevenlabs.voice_configured()


def assistant_variables(name: str, assessment: Mapping[str, Any], directions: Directions) -> dict[str, str]:
    hz = assessment.get("hazard") or {}
    depth = hz.get("depth_in")
    if depth is None:
        depth = hz.get("max_depth_nearby_in")
    reasons = assessment.get("reasons") or []
    return {
        "driver_first_name": first_name(name),
        "street": hz.get("road_name") or "an unknown road",
        "water_depth_in": str(round(depth)) if isinstance(depth, (int, float)) else "unknown",
        "situation": reasons[0] if reasons else "flooding near you",
        "advice": ADVICE["en"].get(str(assessment.get("advice") or "none"), ""),
        "directions": directions.text,
        "call_purpose": "assistant",
    }


async def _assistant_number() -> str | None:
    raw = os.environ.get(NUMBER_ENV, "").strip() or await voice_elevenlabs.agent_phone_number()
    return raw if raw and E164.fullmatch(raw) else None


Emit = Callable[[str, dict[str, Any]], Awaitable[None]]


class AssistantLine:
    """One per safety monitor; at most one live session (the agent's context is global)."""

    def __init__(self, monitor: Any, emit: Emit | None = None, *, poll_s: float = WATCH_POLL_S,
                 max_s: float = WATCH_MAX_S, clock: Callable[[], float] = time.time) -> None:
        self.monitor = monitor
        self.emit = emit
        self.poll_s = poll_s
        self.max_s = max_s
        self.clock = clock
        self._watchers: dict[str, asyncio.Task[None]] = {}
        self._recent: dict[str, tuple[float, dict[str, Any]]] = {}   # uid -> (when, response) for the cooldown
        self._claimed: set[str] = set()                               # conversation ids already attributed
        self._lock = asyncio.Lock()                                   # taps are serialized: one PATCH at a time

    async def _note(self, uid: str, what: str) -> None:
        await asyncio.to_thread(self.monitor.note, uid, what)   # the monitor lock is a threading lock

    async def request(self, uid: str, name: str, assessment: Mapping[str, Any], directions: Directions) -> dict[str, Any]:
        base = {"directions": directions.public()}
        if not live_enabled():
            await self._note(uid, "assistant call requested (simulated)")
            return {**base, "mode": "mock", "phone": None}
        async with self._lock:
            recent = self._recent.get(uid)
            if recent and self.clock() - recent[0] < COOLDOWN_S:
                return {**recent[1], **base}
            out = await self._open_session(uid, name, assessment, directions, base)
            self._recent[uid] = (self.clock(), out)
            return out

    async def _open_session(self, uid: str, name: str, assessment: Mapping[str, Any], directions: Directions,
                            base: dict[str, Any]) -> dict[str, Any]:
        phone = await _assistant_number()
        if not phone:
            await self._note(uid, "assistant line unavailable")
            return {**base, "mode": "unavailable", "phone": None}
        for other in list(self._watchers):   # one session at a time: a new tap replaces any other
            self._watchers.pop(other).cancel()
        if not await voice_elevenlabs.set_agent_defaults(assistant_variables(name, assessment, directions)):
            log.warning("assistant: agent context not updated; the call will be generic")
            await self._note(uid, "assistant call requested (context not updated)")
        else:
            await self._note(uid, "assistant call requested")
        task = asyncio.ensure_future(self._watch_call(uid, self.clock()))
        self._watchers[uid] = task
        task.add_done_callback(lambda t: self._watchers.pop(uid, None) if self._watchers.get(uid) is t else None)
        return {**base, "mode": "live", "phone": phone}

    async def _find_finished(self, since: float) -> dict[str, Any] | None:
        for c in reversed(await voice_elevenlabs.list_conversations()):   # oldest first: the caller's own call
            cid = str(c.get("conversation_id") or "")
            started = c.get("start_time_unix_secs")
            inbound = c.get("direction") in (None, "inbound")   # never the ladder's outbound calls
            if (cid and cid not in self._claimed and inbound and c.get("status") in FINISHED
                    and isinstance(started, (int, float)) and started >= since - START_SLACK_S):
                self._claimed.add(cid)
                return c
        return None

    async def _conversation(self, row: Mapping[str, Any]) -> dict[str, Any]:
        """The full conversation (with transcript); a list row alone would read as an unanswered call."""
        cid = str(row.get("conversation_id") or "")
        for attempt in range(TRANSCRIPT_RETRIES):
            conv = await voice_elevenlabs.get_conversation(cid)
            if conv and conv.get("transcript"):
                return conv
            if attempt < TRANSCRIPT_RETRIES - 1:
                await asyncio.sleep(self.poll_s)
        log.warning("assistant: no transcript for the finished call; classifying from the summary row")
        return dict(row)

    async def _watch_call(self, uid: str, since: float) -> None:
        deadline = time.monotonic() + self.max_s
        try:
            while time.monotonic() < deadline:
                found = await self._find_finished(since)
                if found:
                    await self._finish(uid, await self._conversation(found))
                    return
                await asyncio.sleep(self.poll_s)
            await self._note(uid, "assistant call not detected")
        except asyncio.CancelledError:
            raise
        except Exception:  # a watcher must never take the monitor down
            log.exception("assistant watcher failed for %s", uid)
        finally:
            if live_enabled():   # nobody else should hear this person's name or street
                await voice_elevenlabs.set_agent_defaults(NEUTRAL)

    async def _finish(self, uid: str, conv: Mapping[str, Any]) -> None:
        outcome = classify_call(dict(conv))
        summary = outcome.summary or ("caller asked for help" if outcome.reply == "need_help" else "no summary")
        await self._note(uid, f"assistant call: {summary}")
        if self.emit:
            await self.emit("user.call", {"user_id": uid, "recipient": "assistant", "answered": outcome.answered,
                                          "reply": outcome.reply, "summary": outcome.summary})
        user = self.monitor.users.get(uid)
        if user is not None and outcome.answered:
            acts = await asyncio.to_thread(self.monitor.call_result, uid, True, outcome.reply, "driver")
            await self.monitor.dispatch_actions(user, acts)
