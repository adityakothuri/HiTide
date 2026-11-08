"""Danger level over time -> outreach actions. Pure: (state, assessment, now) -> (state, actions).

Ladder (config/safety.yaml `ladder`):
  WATCH     one text; repeat only after the cooldown
  WARNING   text with what to do (spoken in-app while driving); a teen's parent gets a copy
  DANGER    "are you safe?" poll -> no reply in poll_to_call_s -> voice call -> no answer in call_to_family_s ->
            emergency contact (text + call)
  CRITICAL  call now (case opens) -> family + responders after critical_family_s (at once if highly vulnerable)
Dedupe: we notify on a level *increase*, or on the same level after its cooldown. A SAFE reply mutes the current
level for safe_mute_s (a higher level always gets through). HELP flags responders and stops the polls.
Back below WARNING for all_clear_hold_s after WARNING+ -> one "all clear", then the episode resets.
Timers shrink by up to ladder.vuln_speedup for vulnerable users.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal, Mapping

from app.config import safety_settings
from safety.danger import DangerAssessment
from safety.levels import Level

Recipient = Literal["driver", "parent", "emergency_contact"]
ActionKind = Literal["text", "poll", "voice", "tts_in_app", "flag_responders", "open_case"]
TIMELINE_MAX = 30


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    recipient: Recipient
    template: str
    level: Level

    def public(self) -> dict[str, Any]:
        return {"kind": self.kind, "recipient": self.recipient, "template": self.template, "level": self.level.label}


@dataclass(frozen=True)
class ResponseState:
    episode_level: Level = Level.NONE
    sent_at: Mapping[int, float] = field(default_factory=dict)   # level -> last notify time
    awaiting_since: float | None = None      # safety question asked, no answer yet
    called_at: float | None = None
    call_unanswered: bool = False
    family_at: float | None = None
    responders_flagged: bool = False
    case_opened_at: float | None = None
    safe_until: float | None = None
    safe_level: Level = Level.NONE
    need_help: bool = False
    clear_since: float | None = None
    reminders: Mapping[int, int] = field(default_factory=dict)   # level -> reminders sent this episode
    timeline: tuple[tuple[float, str], ...] = ()

    def public(self) -> dict[str, Any]:
        return {"episode_level": self.episode_level.label, "awaiting_reply": self.awaiting_since is not None,
                "called": self.called_at is not None, "call_unanswered": self.call_unanswered,
                "family_contacted": self.family_at is not None, "responders_flagged": self.responders_flagged,
                "case_open": self.case_opened_at is not None, "need_help": self.need_help,
                "safe_until": self.safe_until, "timeline": [{"t": t, "what": w} for t, w in self.timeline]}


def _note(s: ResponseState, now: float, what: str) -> tuple[tuple[float, str], ...]:
    return (s.timeline + ((now, what),))[-TIMELINE_MAX:]


@dataclass(frozen=True)
class _Timers:
    poll_to_call: float
    call_to_family: float
    critical_family: float
    safe_mute: float
    all_clear_hold: float
    cooldown: Mapping[int, float]


def timers(a: DangerAssessment, cfg: Mapping[str, Any], scale: float = 1.0) -> _Timers:
    lad = cfg["ladder"]
    v = a.vulnerability
    k = (1.0 - float(lad["vuln_speedup"]) * (1.0 if v.needs_priority else v.score)) * scale
    cd = {int(Level.parse(name)): float(s) * scale for name, s in lad["cooldown_s"].items()}
    return _Timers(float(lad["poll_to_call_s"]) * k, float(lad["call_to_family_s"]) * k,
                   float(lad["critical_family_s"]) * k, float(lad["safe_mute_s"]) * scale,
                   float(lad["all_clear_hold_s"]) * scale, cd)


def _notify(s: ResponseState, a: DangerAssessment, now: float, reminder: bool) -> tuple[ResponseState, list[Action]]:
    lv, v = a.level, a.vulnerability
    driving = a.motion.state == "driving"
    acts: list[Action] = []
    suffix = "_reminder" if reminder else ""
    if lv == Level.WATCH:
        acts.append(Action("tts_in_app" if driving else "text", "driver", "watch" + suffix, lv))
    elif lv == Level.WARNING:
        acts.append(Action("tts_in_app" if driving else "text", "driver",
                           ("turn_around" if a.advice == "turn_around" else "warning") + suffix, lv))
    elif lv == Level.DANGER:
        if driving:
            acts.append(Action("tts_in_app", "driver", "turn_around" if a.advice == "turn_around" else "danger_driving", lv))
        elif v.channel == "voice" and not v.no_voice and s.called_at is None:
            acts.append(Action("voice", "driver", "danger_call", lv))
            s = replace(s, called_at=now)
        else:
            acts.append(Action("poll", "driver", "danger_poll", lv))
        s = replace(s, awaiting_since=s.awaiting_since or now)
    elif lv == Level.CRITICAL:
        if driving:
            acts.append(Action("tts_in_app", "driver", "critical_driving", lv))
        if v.no_voice:
            acts.append(Action("poll", "driver", "critical_poll", lv))
        elif not driving:
            acts.append(Action("voice", "driver", "critical_call", lv))
            s = replace(s, called_at=now)
        if s.case_opened_at is None:
            acts.append(Action("open_case", "driver", "case", lv))
            s = replace(s, case_opened_at=now)
        if v.high and not s.responders_flagged:
            acts.append(Action("flag_responders", "driver", "responders", lv))
            s = replace(s, responders_flagged=True)
        s = replace(s, awaiting_since=s.awaiting_since or now)
    if v.is_teen and lv >= Level.WARNING and not reminder:
        acts.append(Action("text", "parent", "parent_copy", lv))
    sent = dict(s.sent_at)
    sent[int(lv)] = now
    what = ", ".join(f"{x.kind}:{x.template}" for x in acts)
    return replace(s, sent_at=sent, timeline=_note(s, now, f"{lv.label}{' reminder' if reminder else ''} -> {what}")), acts


def _family(s: ResponseState, a: DangerAssessment, now: float, why: str) -> tuple[ResponseState, list[Action]]:
    acts = [Action("text", "emergency_contact", "family_text", a.level)]
    if not a.vulnerability.no_voice:
        acts.append(Action("voice", "emergency_contact", "family_call", a.level))
    flag = a.level >= Level.CRITICAL or s.call_unanswered or a.vulnerability.high
    if flag and not s.responders_flagged:
        acts.append(Action("flag_responders", "driver", "responders", a.level))
    return replace(s, family_at=now, responders_flagged=s.responders_flagged or flag,
                   timeline=_note(s, now, f"family contacted ({why})")), acts


def _escalate_timers(s: ResponseState, a: DangerAssessment, now: float, t: _Timers) -> tuple[ResponseState, list[Action]]:
    acts: list[Action] = []
    if s.need_help or s.awaiting_since is None or a.level < Level.DANGER:
        return s, acts
    waited = now - s.awaiting_since
    driving = a.motion.state == "driving"
    v = a.vulnerability
    if s.called_at is None and not v.no_voice and not driving:
        if waited >= t.poll_to_call or a.location_stale:
            acts.append(Action("voice", "driver", "danger_call", a.level))
            s = replace(s, called_at=now, timeline=_note(s, now, "no reply to poll -> call"))
    if s.family_at is None:
        if s.call_unanswered:
            s, more = _family(s, a, now, "call unanswered")
            acts += more
        elif a.level == Level.CRITICAL and s.case_opened_at is not None and now - s.case_opened_at >= t.critical_family:
            s, more = _family(s, a, now, "critical, no reply")
            acts += more
        elif s.called_at is not None and now - s.called_at >= t.call_to_family:
            s, more = _family(s, a, now, "no reply after call")
            acts += more
        elif v.no_voice and waited >= t.poll_to_call + t.call_to_family:
            s, more = _family(s, a, now, "no reply (text only)")
            acts += more
    return s, acts


def _may_remind(s: ResponseState, lv: Level, cfg: Mapping[str, Any]) -> bool:
    """Reminders stop once someone else owns the case (help requested, or family and responders both engaged),
    and after ladder.max_reminders at this level."""
    if s.need_help or (s.family_at is not None and s.responders_flagged):
        return False
    return s.reminders.get(int(lv), 0) < int(cfg["ladder"].get("max_reminders", 2))


def decide(s: ResponseState, a: DangerAssessment, now: float, cfg: Mapping[str, Any] | None = None,
           scale: float = 1.0) -> tuple[ResponseState, list[Action]]:
    c: Mapping[str, Any] = cfg if cfg is not None else safety_settings()
    t = timers(a, c, scale)
    lv = a.level
    acts: list[Action] = []
    muted = s.safe_until is not None and now < s.safe_until and lv <= s.safe_level
    if lv >= Level.WARNING and s.clear_since is not None:
        s = replace(s, clear_since=None)          # a flap back up restarts the all-clear hold
    if lv > s.episode_level:
        s, acts = _notify(replace(s, episode_level=lv, clear_since=None), a, now, reminder=False)
    elif lv >= Level.WATCH and lv == s.episode_level and not muted and _may_remind(s, lv, c):
        last = s.sent_at.get(int(lv))
        if last is not None and now - last >= t.cooldown.get(int(lv), float("inf")):
            s, acts = _notify(s, a, now, reminder=True)
            s = replace(s, reminders={**s.reminders, int(lv): s.reminders.get(int(lv), 0) + 1})
    if not muted:
        s, more = _escalate_timers(s, a, now, t)
        acts += more
    # De-escalation: below WARNING long enough after WARNING+ -> all clear, new episode.
    # Never "all clear" someone who asked for help or has an open case (an operator closes those), and never
    # because the evidence went dark: hold while any source is degraded.
    holding = s.need_help or s.case_opened_at is not None or bool(a.hazard.degraded_sources)
    if lv < Level.WARNING and s.episode_level >= Level.WARNING and not holding:
        since = s.clear_since if s.clear_since is not None else now
        if now - since >= t.all_clear_hold:
            acts.append(Action("text", "driver", "all_clear", lv))
            s = ResponseState(episode_level=lv, sent_at={int(lv): now} if lv > Level.NONE else {},
                              timeline=_note(s, now, "all clear"))
        else:
            s = replace(s, clear_since=since)
    elif lv == Level.NONE and s.episode_level == Level.WATCH:
        s = ResponseState(timeline=s.timeline)   # a watch that passed: reset quietly
    return s, acts


def apply_reply(s: ResponseState, kind: str, now: float, by: str, a: DangerAssessment | None,
                cfg: Mapping[str, Any] | None = None, scale: float = 1.0) -> tuple[ResponseState, list[Action]]:
    """SAFE / HELP from the driver or their emergency contact (text, poll vote, or what the voice agent collected)."""
    c: Mapping[str, Any] = cfg if cfg is not None else safety_settings()
    lv = s.episode_level
    if kind == "need_help":
        acts = [Action("text", "driver", "ack_help", lv)]
        if not s.responders_flagged:
            acts.append(Action("flag_responders", "driver", "responders", lv))
        return replace(s, need_help=True, responders_flagged=True, awaiting_since=None,
                       timeline=_note(s, now, f"HELP from {by} -> responders flagged")), acts
    if kind == "safe" and by != "driver":
        # Family saying "she's fine" is a note for responders, not a reason to stop checking on the driver.
        return replace(s, timeline=_note(s, now, f"SAFE from {by} (noted; driver not yet confirmed)")), []
    if kind == "safe":
        if s.need_help:   # HELP beats a later SAFE until an operator clears it
            return replace(s, timeline=_note(s, now, f"SAFE from {by} ignored: help already requested")), []
        mute = float(c["ladder"]["safe_mute_s"]) * scale
        return replace(s, awaiting_since=None, safe_until=now + mute, safe_level=lv, call_unanswered=False,
                       timeline=_note(s, now, f"SAFE from {by}")), [Action("text", "driver", "ack_safe", lv)]
    return s, []


def apply_call_result(s: ResponseState, answered: bool, reply: str | None, now: float, by: str,
                      a: DangerAssessment | None, cfg: Mapping[str, Any] | None = None,
                      scale: float = 1.0) -> tuple[ResponseState, list[Action]]:
    if reply in ("safe", "need_help"):
        return apply_reply(s, reply, now, by, a, cfg, scale)
    if not answered and by == "driver":
        return replace(s, call_unanswered=True, timeline=_note(s, now, "call unanswered")), []
    return replace(s, timeline=_note(s, now, f"call to {by} ended without a clear answer")), []


# ---- persistence (SpacetimeDB response_state) --------------------------------------
def response_to_dict(s: ResponseState) -> dict[str, Any]:
    return {"episode_level": int(s.episode_level), "sent_at": {str(k): v for k, v in s.sent_at.items()},
            "awaiting_since": s.awaiting_since, "called_at": s.called_at, "call_unanswered": s.call_unanswered,
            "family_at": s.family_at, "responders_flagged": s.responders_flagged, "case_opened_at": s.case_opened_at,
            "safe_until": s.safe_until, "safe_level": int(s.safe_level), "need_help": s.need_help,
            "clear_since": s.clear_since, "reminders": {str(k): v for k, v in s.reminders.items()},
            "timeline": [[t, w] for t, w in s.timeline]}


def response_from_dict(d: Mapping[str, Any]) -> ResponseState:
    return ResponseState(
        episode_level=Level(int(d.get("episode_level", 0))),
        sent_at={int(k): float(v) for k, v in (d.get("sent_at") or {}).items()},
        awaiting_since=d.get("awaiting_since"), called_at=d.get("called_at"),
        call_unanswered=bool(d.get("call_unanswered")), family_at=d.get("family_at"),
        responders_flagged=bool(d.get("responders_flagged")), case_opened_at=d.get("case_opened_at"),
        safe_until=d.get("safe_until"), safe_level=Level(int(d.get("safe_level", 0))),
        need_help=bool(d.get("need_help")), clear_since=d.get("clear_since"),
        reminders={int(k): int(v) for k, v in (d.get("reminders") or {}).items()},
        timeline=tuple((float(t), str(w)) for t, w in (d.get("timeline") or [])))
