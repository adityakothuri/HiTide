"""Stage 3 case state machine. Pure and immutable: every function returns a new Case.

States only move forward; out-of-order events are ignored. See vault/Modules for the flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from api.schemas import Case, LatLon, ResponderView, TimelineEntry, VisionResult
from scoring.risk import RiskScore

TimerKind = Literal["call_driver", "contact_family", "dispatch_drone"]
ReplyKind = Literal["safe", "need_help"]
ReplyBy = Literal["driver", "emergency_contact"]

STATE_ORDER = (
    "monitoring",
    "calling",
    "contacting_family",
    "drone_en_route",
    "verified",
    "handed_to_responders",
    "resolved",
)
_DRONE_DISPATCH_FROM = ("calling", "contacting_family")
_REPLY_ESCALATES_FROM = ("monitoring", "calling")
_REPLIER_LABEL = {"driver": "Driver", "emergency_contact": "Emergency contact"}


@dataclass(frozen=True)
class Open:
    now_iso: str
    t_s: float


@dataclass(frozen=True)
class Timer:
    kind: TimerKind
    t_s: float


@dataclass(frozen=True)
class DroneArrived:
    vision: VisionResult | None
    people_count: int | None
    t_s: float


@dataclass(frozen=True)
class Handoff:
    t_s: float


@dataclass(frozen=True)
class Reply:
    kind: ReplyKind
    by: ReplyBy
    t_s: float


Event = Open | Timer | DroneArrived | Handoff | Reply


def _entry(now_iso: str, t_s: float, kind: str, text: str) -> TimelineEntry:
    return TimelineEntry(ts=now_iso, t_case_s=t_s, kind=kind, text=text)


def _append(case: Case, *entries: TimelineEntry, **update: object) -> Case:
    return case.model_copy(update={**update, "timeline": [*case.timeline, *entries]})


def _flag(case: Case, now_iso: str, t_s: float, why: str) -> Case:
    """Set responder_flag (with a timeline entry) only if not already set."""
    if case.responder_flag:
        return case
    return _append(case, _entry(now_iso, t_s, "flag", why), responder_flag=True)


def _hand_off(case: Case, now_iso: str, t_s: float) -> Case:
    return _append(
        case,
        _entry(now_iso, t_s, "state", "Handed to responders"),
        state="handed_to_responders",
    )


def open_case(
    case_id: str,
    driver_id: str,
    driver_name: str,
    lat: float,
    lon: float,
    depth_in: float,
    risk: RiskScore,
    now_iso: str,
) -> Case:
    case = Case(
        id=case_id,
        driver_id=driver_id,
        driver_name=driver_name,
        state="monitoring",
        urgency=risk.value,
        urgency_reasons=list(risk.reasons),
        responder_flag=False,
        location=LatLon(lat=lat, lon=lon),
        depth_in=depth_in,
        opened_at=now_iso,
        timeline=[_entry(now_iso, 0.0, "state", "Car stopped in floodwater")],
        responder_view=ResponderView(
            location=LatLon(lat=lat, lon=lon), people_count=None, water_depth_in=depth_in
        ),
    )
    if risk.high_risk:
        return _flag(case, now_iso, 0.0, "High risk: responders flagged immediately")
    return case


def _on_timer(case: Case, ev: Timer, now_iso: str) -> Case:
    if ev.kind == "call_driver" and case.state == "monitoring":
        return _append(
            case, _entry(now_iso, ev.t_s, "state", "Calling driver"), state="calling"
        )
    if ev.kind == "contact_family" and case.state == "calling":
        moved = _append(
            case,
            _entry(now_iso, ev.t_s, "state", "Contacting family"),
            state="contacting_family",
        )
        return _flag(moved, now_iso, ev.t_s, "No answer: responders flagged")
    if ev.kind == "dispatch_drone" and case.state in _DRONE_DISPATCH_FROM:
        return _append(
            case,
            _entry(now_iso, ev.t_s, "drone", "Drone dispatched"),
            state="drone_en_route",
        )
    return case


def _on_drone_arrived(case: Case, ev: DroneArrived, now_iso: str) -> Case:
    if case.state != "drone_en_route":
        return case
    view = case.responder_view.model_copy(update={"people_count": ev.people_count})
    verified = _append(
        case,
        _entry(now_iso, ev.t_s, "vision", "Drone verified scene"),
        state="verified",
        vision=ev.vision,
        responder_view=view,
    )
    return _hand_off(verified, now_iso, ev.t_s) if verified.responder_flag else verified


def _on_handoff(case: Case, ev: Handoff, now_iso: str) -> Case:
    if case.state == "handed_to_responders":
        return case
    return _hand_off(case, now_iso, ev.t_s)


def _on_reply(case: Case, ev: Reply, now_iso: str) -> Case:
    who = _REPLIER_LABEL[ev.by]
    if ev.kind == "safe":
        recalled = "; drone recalled" if case.state == "drone_en_route" else ""
        return _append(
            case,
            _entry(now_iso, ev.t_s, "reply", f"{who} replied safe{recalled}"),
            state="resolved",
        )
    replied = _append(case, _entry(now_iso, ev.t_s, "reply", f"{who} needs help"))
    flagged = _flag(replied, now_iso, ev.t_s, "Help requested: responders flagged")
    if case.state in _REPLY_ESCALATES_FROM:
        return _hand_off(flagged, now_iso, ev.t_s)
    return flagged


def transition(case: Case, event: Event, now_iso: str) -> Case:
    """Apply one event. Returns the same case object when the event is ignored."""
    if case.state == "resolved":
        return case
    if isinstance(event, Timer):
        return _on_timer(case, event, now_iso)
    if isinstance(event, DroneArrived):
        return _on_drone_arrived(case, event, now_iso)
    if isinstance(event, Handoff):
        return _on_handoff(case, event, now_iso)
    if isinstance(event, Reply):
        return _on_reply(case, event, now_iso)
    return case


def due_timers(
    case: Case, elapsed_s: float, fired: frozenset[str], profile: dict[str, float]
) -> list[str]:
    """Timer kinds whose threshold has passed and that have not fired, earliest first."""
    if case.state == "resolved":
        return []
    ready = [
        (threshold, kind)
        for kind, threshold in profile.items()
        if threshold <= elapsed_s and kind not in fired
    ]
    return [kind for _, kind in sorted(ready)]
