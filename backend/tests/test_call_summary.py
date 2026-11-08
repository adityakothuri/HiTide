"""Pure classification of an ElevenLabs conversation payload, plus follow-up text helpers."""

from __future__ import annotations

import pytest

from outreach.call_summary import (
    CallOutcome,
    call_variables,
    classify_call,
    follow_up_text,
    opening_line,
)


def _conv(status="done", users=(), driver_status=None, summary="", termination=""):
    transcript = [{"role": "agent", "message": "Are you safe?"}]
    transcript += [{"role": "user", "message": u} for u in users]
    analysis: dict = {"transcript_summary": summary}
    if driver_status is not None:
        analysis["data_collection_results"] = {"driver_status": {"value": driver_status}}
    return {"status": status, "transcript": transcript, "analysis": analysis,
            "metadata": {"termination_reason": termination}}


def test_data_collection_safe_wins_over_transcript():
    out = classify_call(_conv(users=["help me"], driver_status="safe", summary="She is fine."))
    assert out == CallOutcome(reply="safe", summary="She is fine.", answered=True)


def test_data_collection_need_help():
    assert classify_call(_conv(users=["hello"], driver_status="need_help")).reply == "need_help"


def test_unknown_data_collection_falls_back_to_transcript():
    assert classify_call(_conv(users=["I'm okay"], driver_status="unknown")).reply == "safe"


def test_transcript_danger_beats_ambiguity():
    out = classify_call(_conv(users=["I'm fine", "actually the water is rising, help"]))
    assert out.reply == "need_help"


def test_agent_turns_ignored():
    conv = _conv(users=["hmm"])
    conv["transcript"][0]["message"] = "Reply safe or help"
    assert classify_call(conv).reply is None


def test_no_user_turns_is_unanswered():
    out = classify_call(_conv(users=[]))
    assert out.answered is False and out.reply is None


def test_blank_user_turns_do_not_count_as_answered():
    conv = _conv(users=[])
    conv["transcript"].append({"role": "user", "message": None})
    assert classify_call(conv).answered is False


def test_failed_status_unanswered_with_call_ended_line():
    out = classify_call(_conv(status="failed", users=["help"]))
    assert out.answered is False and out.reply is None
    assert out.summary.startswith("Call ended:")


def test_voicemail_termination_unanswered():
    out = classify_call(_conv(users=["leave a message after the beep"], termination="voicemail_detected"))
    assert out.answered is False and out.reply is None


def test_summary_fallback_when_missing():
    out = classify_call(_conv(users=["ok"], summary=""))
    assert out.summary.startswith("Call ended:") and out.reply == "safe"


@pytest.mark.parametrize("bad", [None, {}, {"transcript": None, "analysis": None}, "x", []])
def test_malformed_payload_never_raises(bad):
    out = classify_call(bad)  # type: ignore[arg-type]
    assert out.reply is None and out.answered is False


def test_follow_up_need_help_mentions_call_and_safety():
    t = follow_up_text(CallOutcome("need_help", "s", True), "Water St")
    assert "Following up on our call" in t and "need help" in t and "roof" in t


def test_follow_up_safe_mentions_street():
    t = follow_up_text(CallOutcome("safe", "s", True), "Water St")
    assert "Glad you're safe" in t and "Water St" in t


def test_follow_up_unanswered_says_missed():
    t = follow_up_text(CallOutcome(None, "s", False), "Water St")
    assert "missed" in t.lower() and "SAFE" in t


def test_follow_up_answered_but_unclear():
    t = follow_up_text(CallOutcome(None, "s", True), "Water St")
    assert "Following up on our call" in t and "SAFE" in t


def test_call_variables_and_opening_line():
    v = call_variables("Margaret Hale", "Water St", 23.6)
    assert v == {"driver_first_name": "Margaret", "street": "Water St", "water_depth_in": "24", "call_purpose": "driver"}
    assert opening_line("Margaret", "Water St") == (
        "Hi Margaret, this is State Farm Flood Watch. Your car looks stopped in floodwater on Water St. Are you safe?")
