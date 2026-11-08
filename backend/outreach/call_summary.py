"""Pure helpers: turn an ElevenLabs conversation payload into a case outcome and a text follow-up."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from outreach.replies import parse_reply

Reply = Literal["safe", "need_help"]
_UNANSWERED_STATUSES = frozenset({"failed"})
_VOICEMAIL_MARKERS = ("voicemail", "machine")


@dataclass(frozen=True)
class CallOutcome:
    reply: Reply | None
    summary: str
    answered: bool


def _user_turns(conversation: dict[str, Any]) -> list[str]:
    turns = conversation.get("transcript")
    if not isinstance(turns, list):
        return []
    return [t["message"].strip() for t in turns
            if isinstance(t, dict) and t.get("role") == "user"
            and isinstance(t.get("message"), str) and t["message"].strip()]


def _termination(conversation: dict[str, Any]) -> str:
    meta = conversation.get("metadata")
    reason = meta.get("termination_reason") if isinstance(meta, dict) else ""
    return reason.lower() if isinstance(reason, str) else ""


def _collected_status(conversation: dict[str, Any]) -> Reply | None:
    analysis = conversation.get("analysis")
    results = analysis.get("data_collection_results") if isinstance(analysis, dict) else None
    item = results.get("driver_status") if isinstance(results, dict) else None
    value = item.get("value") if isinstance(item, dict) else None
    return value if value in ("safe", "need_help") else None


def _transcript_reply(turns: list[str]) -> Reply | None:
    replies = [parse_reply(t) for t in turns]
    if "need_help" in replies:  # danger beats ambiguity
        return "need_help"
    return "safe" if "safe" in replies else None


def _summary(conversation: dict[str, Any], status: str, answered: bool) -> str:
    analysis = conversation.get("analysis")
    text = analysis.get("transcript_summary") if isinstance(analysis, dict) else None
    if isinstance(text, str) and text.strip():
        return text.strip()
    if not answered:
        return f"Call ended: no answer ({status or 'unknown'})"
    return "Call ended: driver answered, no summary available"


def classify_call(conversation: dict[str, Any]) -> CallOutcome:
    """Never raises; malformed input is an unanswered call."""
    if not isinstance(conversation, dict):
        return CallOutcome(None, "Call ended: no data", False)
    status = conversation.get("status")
    status = status if isinstance(status, str) else ""
    turns = _user_turns(conversation)
    voicemail = any(m in _termination(conversation) for m in _VOICEMAIL_MARKERS)
    answered = bool(turns) and status not in _UNANSWERED_STATUSES and not voicemail
    if not answered:
        return CallOutcome(None, _summary(conversation, status, False), False)
    reply = _collected_status(conversation) or _transcript_reply(turns)
    return CallOutcome(reply, _summary(conversation, status, True), True)


def first_name(full_name: str) -> str:
    parts = full_name.split()
    return parts[0] if parts else "there"


def call_variables(driver_name: str, street: str, depth_in: float) -> dict[str, str]:
    return {"driver_first_name": first_name(driver_name), "street": street,
            "water_depth_in": str(round(depth_in))}


def opening_line(first: str, street: str) -> str:
    return (f"Hi {first}, this is State Farm Flood Watch. Your car looks stopped in floodwater on {street}. "
            "Are you safe?")


def follow_up_text(outcome: CallOutcome, street: str) -> str:
    if outcome.reply == "need_help":
        return ("Following up on our call: you said you need help. Responders are on the way. Stay in the car "
                "only if water is below the doors; otherwise get on the roof.")
    if outcome.reply == "safe":
        return f"Glad you're safe. Following up on our call: avoid {street} until the water drops."
    if outcome.answered:
        return ("Following up on our call: we couldn't tell if you're okay. Reply SAFE if you are, or HELP "
                "if you need us. Responders are being notified.")
    return ("State Farm Flood Watch: we missed you on our call. Reply SAFE if you're okay, or HELP if you "
            "need us. Responders are being notified.")
