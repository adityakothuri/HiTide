"""The outreach ladder: right channel at the right level, no duplicates, replies change course."""

from app.config import safety_settings
from safety.levels import Level
from safety.policy import ResponseState, apply_call_result, apply_reply, decide, timers
from tests.safety_helpers import assessment, vuln

CFG = safety_settings()


def kinds(acts):
    return [(a.kind, a.recipient, a.template) for a in acts]


def run(levels_at, v=None, state="parked", replies=()):
    """levels_at: [(t, Level)]. replies: [(t, kind)]. Returns (final state, [(t, actions)])."""
    s, log = ResponseState(), []
    rep = dict(replies)
    for t, lv in levels_at:
        if t in rep:
            s, acts = apply_reply(s, rep[t], t, "driver", None, CFG)
            log.append((t, acts))
        s, acts = decide(s, assessment(lv, v, state, now=t), t, CFG)
        log.append((t, acts))
    return s, log


def test_watch_sends_one_text_and_respects_cooldown():
    s, log = run([(t, Level.WATCH) for t in range(0, 3600, 60)])
    sent = [a for _, acts in log for a in acts]
    assert kinds(sent) == [("text", "driver", "watch")]


def test_warning_text_parked_spoken_when_driving():
    _, log = run([(0, Level.WARNING)])
    assert kinds(log[0][1]) == [("text", "driver", "warning")]
    _, log = run([(0, Level.WARNING)], state="driving")
    assert log[0][1][0].kind == "tts_in_app"


def test_danger_poll_then_call_then_family():
    t = timers(assessment(Level.DANGER), CFG)
    seq = [(0, Level.DANGER), (t.poll_to_call + 1, Level.DANGER), (t.poll_to_call + t.call_to_family + 2, Level.DANGER)]
    s, log = run(seq)
    assert kinds(log[0][1]) == [("poll", "driver", "danger_poll")]
    assert kinds(log[1][1]) == [("voice", "driver", "danger_call")]
    assert ("text", "emergency_contact", "family_text") in kinds(log[2][1])
    assert ("voice", "emergency_contact", "family_call") in kinds(log[2][1])
    assert s.family_at is not None


def test_safe_reply_stops_the_ladder_and_mutes_the_level():
    t = timers(assessment(Level.DANGER), CFG)
    mute = CFG["ladder"]["safe_mute_s"]
    seq = [(0, Level.DANGER), (10, Level.DANGER), (t.poll_to_call + 50, Level.DANGER), (mute - 10, Level.DANGER)]
    s, log = run(seq, replies=[(10, "safe")])
    sent = [k for _, acts in log for k in kinds(acts)]
    assert ("voice", "driver", "danger_call") not in sent
    assert ("text", "driver", "ack_safe") in sent
    assert s.awaiting_since is None
    # After the mute, a still-dangerous situation is asked about again (once per cooldown, capped).
    s, acts = decide(s, assessment(Level.DANGER, now=t.cooldown[3] + 100), t.cooldown[3] + 100, CFG)
    assert kinds(acts) == [("poll", "driver", "danger_poll")]


def test_higher_level_breaks_through_a_safe_mute():
    s, log = run([(0, Level.DANGER), (10, Level.DANGER), (20, Level.CRITICAL)], replies=[(10, "safe")])
    assert ("voice", "driver", "critical_call") in kinds(log[-1][1])


def test_help_flags_responders_once_and_beats_a_later_safe():
    s = ResponseState(episode_level=Level.DANGER)
    s, acts = apply_reply(s, "need_help", 5, "driver", None, CFG)
    assert s.need_help and s.responders_flagged and ("flag_responders", "driver", "responders") in kinds(acts)
    s2, acts2 = apply_reply(s, "safe", 6, "driver", None, CFG)
    assert s2.need_help and acts2 == []


def test_critical_opens_a_case_calls_and_brings_family_and_responders():
    t = timers(assessment(Level.CRITICAL), CFG)
    s, log = run([(0, Level.CRITICAL), (t.critical_family + 1, Level.CRITICAL)])
    first = kinds(log[0][1])
    assert ("voice", "driver", "critical_call") in first and ("open_case", "driver", "case") in first
    later = kinds(log[1][1])
    assert ("text", "emergency_contact", "family_text") in later and ("flag_responders", "driver", "responders") in later


def test_highly_vulnerable_get_responders_at_once_and_faster_timers():
    v = vuln(score=0.9, band="high", needs=True)
    _, log = run([(0, Level.CRITICAL)], v=v)
    assert ("flag_responders", "driver", "responders") in kinds(log[0][1])
    assert timers(assessment(Level.DANGER, v), CFG).poll_to_call < timers(assessment(Level.DANGER), CFG).poll_to_call


def test_no_voice_users_are_never_called():
    v = vuln(no_voice=True, channel="sms")
    seq = [(t, Level.CRITICAL) for t in range(0, 4000, 30)]
    _, log = run(seq, v=v)
    sent = [k for _, acts in log for k in kinds(acts)]
    assert not any(kind == "voice" and who == "driver" for kind, who, _ in sent)
    assert ("poll", "driver", "critical_poll") in sent
    assert ("text", "emergency_contact", "family_text") in sent


def test_unanswered_call_goes_straight_to_family():
    s, _ = run([(0, Level.DANGER)], v=vuln(channel="voice"))
    assert s.called_at == 0
    s, _ = apply_call_result(s, answered=False, reply=None, now=30, by="driver", a=None, cfg=CFG)
    s, acts = decide(s, assessment(Level.DANGER, vuln(channel="voice"), now=31), 31, CFG)
    assert ("text", "emergency_contact", "family_text") in kinds(acts)


def test_voice_agent_collected_safe_is_a_reply():
    s, _ = run([(0, Level.DANGER)], v=vuln(channel="voice"))
    s, acts = apply_call_result(s, answered=True, reply="safe", now=40, by="driver", a=None, cfg=CFG)
    assert s.safe_until is not None and ("text", "driver", "ack_safe") in kinds(acts)


def test_teen_parent_gets_a_copy_once():
    _, log = run([(0, Level.WARNING), (CFG["ladder"]["cooldown_s"]["warning"] + 1, Level.WARNING)], v=vuln(teen=True))
    sent = [k for _, acts in log for k in kinds(acts)]
    assert sent.count(("text", "parent", "parent_copy")) == 1


def test_reminders_capped_per_level():
    cd = CFG["ladder"]["cooldown_s"]["warning"]
    _, log = run([(k * (cd + 1), Level.WARNING) for k in range(10)])
    sent = [k for _, acts in log for k in kinds(acts)]
    assert len(sent) == 1 + CFG["ladder"]["max_reminders"]


def test_all_clear_once_after_hold_then_new_episode():
    hold = CFG["ladder"]["all_clear_hold_s"]
    seq = [(0, Level.DANGER), (100, Level.NONE), (100 + hold + 1, Level.NONE), (100 + 2 * hold, Level.NONE),
           (100 + 3 * hold, Level.WARNING)]
    s, log = run(seq, replies=[(100, "safe")])
    sent = [k for _, acts in log for k in kinds(acts)]
    assert sent.count(("text", "driver", "all_clear")) == 1
    assert ("text", "driver", "warning") in sent and s.episode_level == Level.WARNING


def test_never_duplicates_same_level_within_cooldown():
    _, log = run([(t, Level.DANGER) for t in range(0, 200, 5)], replies=[(1, "safe")])
    polls = [k for _, acts in log for k in kinds(acts) if k[0] == "poll"]
    assert len(polls) == 1


def test_flap_back_up_restarts_the_all_clear_hold():
    hold = CFG["ladder"]["all_clear_hold_s"]
    seq = [(0, Level.DANGER), (10, Level.NONE), (20, Level.WARNING), (hold + 15, Level.NONE)]
    _, log = run(seq, replies=[(10, "safe")])
    assert ("text", "driver", "all_clear") not in [k for _, acts in log for k in kinds(acts)]


def test_no_all_clear_after_help_or_with_an_open_case():
    hold = CFG["ladder"]["all_clear_hold_s"]
    s, log = run([(0, Level.DANGER), (10, Level.NONE), (hold + 20, Level.NONE)], replies=[(10, "need_help")])
    assert ("text", "driver", "all_clear") not in [k for _, acts in log for k in kinds(acts)]
    assert s.need_help and s.responders_flagged


def test_no_all_clear_while_evidence_is_dark():
    from dataclasses import replace as dc_replace
    hold = CFG["ladder"]["all_clear_hold_s"]
    s, _ = run([(0, Level.WARNING)])
    for t in (10, hold + 20):
        a = assessment(Level.NONE, now=t)
        a = dc_replace(a, hazard=dc_replace(a.hazard, degraded_sources=("usgs_gage",)))
        s, acts = decide(s, a, t, CFG)
        assert acts == []


def test_family_safe_is_a_note_not_a_mute():
    s, _ = run([(0, Level.DANGER)])
    s2, acts = apply_reply(s, "safe", 5, "emergency_contact", None, CFG)
    assert acts == [] and s2.safe_until is None and s2.awaiting_since is not None
