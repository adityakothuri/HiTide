from __future__ import annotations

import pytest

from api.schemas import VisionResult
from scoring.risk import RiskScore
from stages.escalation import (
    DroneArrived,
    Handoff,
    Open,
    Reply,
    Timer,
    due_timers,
    open_case,
    transition,
)

NOW = "2026-07-04T05:00:00+00:00"
DEMO = {"call_driver": 0, "contact_family": 12, "dispatch_drone": 18}
ORDER = [
    "monitoring",
    "calling",
    "contacting_family",
    "drone_en_route",
    "verified",
    "handed_to_responders",
    "resolved",
]


def risk(high: bool = False) -> RiskScore:
    return RiskScore(
        value=0.8 if high else 0.3,
        reasons=("deep water",) if high else (),
        high_risk=high,
        notify_parent=False,
        factors={},
    )


def vision() -> VisionResult:
    return VisionResult(
        image_url="/static/drone/a.jpg",
        annotated_url="/static/drone/a_ann.jpg",
        car_detected=True,
        water_level="doors",
        water_level_source="rule",
        people=[{"placement": "on_roof", "box": [0, 0, 1, 1], "conf": 0.9}],
        night_mode=False,
        thermal_simulated=False,
        recommendation="boat_required",
    )


def mk(high: bool = False):
    return open_case("c1", "d1", "Dana", 30.05, -99.14, 8.0, risk(high), NOW)


def kinds(case):
    return [e.kind for e in case.timeline]


def at(case, state):
    """Drive a low-risk case to `state` via timers."""
    steps = {
        "calling": [Timer("call_driver", 0)],
        "contacting_family": [Timer("call_driver", 0), Timer("contact_family", 12)],
        "drone_en_route": [
            Timer("call_driver", 0),
            Timer("contact_family", 12),
            Timer("dispatch_drone", 18),
        ],
    }
    for ev in steps.get(state, []):
        case = transition(case, ev, NOW)
    assert case.state == state
    return case


# ---------- open_case ----------


def test_open_case_low_risk():
    c = mk()
    assert c.state == "monitoring"
    assert c.responder_flag is False
    assert [e.text for e in c.timeline] == ["Car stopped in floodwater"]
    assert c.timeline[0].ts == NOW and c.timeline[0].t_case_s == 0
    assert c.urgency == 0.3
    assert c.depth_in == 8.0
    assert c.opened_at == NOW
    assert (c.id, c.driver_id, c.driver_name) == ("c1", "d1", "Dana")


def test_open_case_high_risk_flags_immediately():
    c = mk(high=True)
    assert c.responder_flag is True
    assert kinds(c) == ["state", "flag"]
    assert c.state == "monitoring"
    assert c.urgency_reasons == ["deep water"]


def test_responder_view_privacy_fields_only():
    c = mk()
    assert set(type(c.responder_view).model_fields) == {
        "location",
        "people_count",
        "water_depth_in",
    }
    assert c.responder_view.location.lat == 30.05
    assert c.responder_view.people_count is None
    assert c.responder_view.water_depth_in == 8.0


# ---------- happy path ----------


def test_full_happy_path_in_order():
    c = mk()
    seen = [c.state]
    for ev in (
        Timer("call_driver", 0),
        Timer("contact_family", 12),
        Timer("dispatch_drone", 18),
        DroneArrived(vision(), 2, 30),
        Handoff(31),
    ):
        c = transition(c, ev, NOW)
        seen.append(c.state)
    # low risk but flagged at contact_family => drone arrival auto-hands off
    assert seen == [
        "monitoring",
        "calling",
        "contacting_family",
        "drone_en_route",
        "handed_to_responders",
        "handed_to_responders",
    ]
    c2 = transition(c, Reply("safe", "driver", 40), NOW)
    assert c2.state == "resolved"


def test_drone_arrival_verifies_then_hands_off_when_flagged():
    c = at(mk(), "drone_en_route")
    assert c.responder_flag is True
    n = len(c.timeline)
    c = transition(c, DroneArrived(vision(), 3, 30), NOW)
    assert c.state == "handed_to_responders"
    assert len(c.timeline) == n + 2
    assert c.vision == vision()
    assert c.responder_view.people_count == 3


def test_drone_arrival_stays_verified_when_not_flagged():
    # drone dispatched straight from calling: never flagged
    c = transition(transition(mk(), Timer("call_driver", 0), NOW), Timer("dispatch_drone", 18), NOW)
    assert c.state == "drone_en_route" and c.responder_flag is False
    c = transition(c, DroneArrived(vision(), 1, 20), NOW)
    assert c.state == "verified"
    assert c.responder_view.people_count == 1


def test_drone_arrival_with_no_vision_or_count():
    c = transition(transition(mk(), Timer("call_driver", 0), NOW), Timer("dispatch_drone", 18), NOW)
    c = transition(c, DroneArrived(None, None, 20), NOW)
    assert c.state == "verified"
    assert c.vision is None
    assert c.responder_view.people_count is None


def test_drone_arrival_ignored_unless_en_route():
    c = mk()
    assert transition(c, DroneArrived(vision(), 2, 5), NOW) == c


# ---------- flags ----------


def test_low_risk_flagged_at_contact_family():
    c = at(mk(), "calling")
    assert c.responder_flag is False
    c = transition(c, Timer("contact_family", 12), NOW)
    assert c.responder_flag is True
    assert kinds(c)[-1] == "flag" or "flag" in kinds(c)
    assert kinds(c).count("flag") == 1


def test_contact_family_does_not_double_flag_high_risk():
    c = transition(mk(high=True), Timer("call_driver", 0), NOW)
    c = transition(c, Timer("contact_family", 12), NOW)
    assert c.state == "contacting_family"
    assert kinds(c).count("flag") == 1


def test_dispatch_drone_does_not_block_flag():
    c = at(mk(), "contacting_family")
    c = transition(c, Timer("dispatch_drone", 18), NOW)
    assert c.state == "drone_en_route"
    assert c.responder_flag is True


def test_dispatch_drone_from_monitoring_ignored():
    c = mk()
    assert transition(c, Timer("dispatch_drone", 18), NOW) == c


# ---------- handoff ----------


@pytest.mark.parametrize("state", ["monitoring", "calling", "contacting_family", "drone_en_route"])
def test_handoff_from_any_non_resolved(state):
    c = at(mk(), state)
    c = transition(c, Handoff(50), NOW)
    assert c.state == "handed_to_responders"
    assert c.timeline[-1].t_case_s == 50


# ---------- replies ----------


@pytest.mark.parametrize("state", ["monitoring", "calling", "contacting_family", "drone_en_route"])
@pytest.mark.parametrize("by", ["driver", "emergency_contact"])
def test_safe_reply_resolves_at_each_stage(state, by):
    c = at(mk(), state)
    c = transition(c, Reply("safe", by, 60), NOW)
    assert c.state == "resolved"
    assert c.timeline[-1].kind == "reply"


def test_safe_reply_resolves_from_verified_and_handed():
    c = transition(transition(mk(), Timer("call_driver", 0), NOW), Timer("dispatch_drone", 18), NOW)
    v = transition(c, DroneArrived(vision(), 1, 20), NOW)
    assert v.state == "verified"
    assert transition(v, Reply("safe", "driver", 30), NOW).state == "resolved"
    h = transition(mk(), Handoff(5), NOW)
    assert transition(h, Reply("safe", "driver", 30), NOW).state == "resolved"


def test_safe_reply_notes_drone_recalled():
    c = at(mk(), "drone_en_route")
    c = transition(c, Reply("safe", "driver", 25), NOW)
    assert "drone recalled" in c.timeline[-1].text.lower()


def test_safe_reply_without_drone_has_no_recall_note():
    c = at(mk(), "calling")
    c = transition(c, Reply("safe", "driver", 5), NOW)
    assert "recalled" not in c.timeline[-1].text.lower()


@pytest.mark.parametrize("state", ["monitoring", "calling"])
def test_need_help_jumps_to_handoff(state):
    c = at(mk(), state)
    c = transition(c, Reply("need_help", "driver", 5), NOW)
    assert c.responder_flag is True
    assert c.state == "handed_to_responders"
    assert "reply" in kinds(c)


@pytest.mark.parametrize("state", ["contacting_family", "drone_en_route"])
def test_need_help_does_not_move_backward_or_forward(state):
    c = at(mk(), state)
    c = transition(c, Reply("need_help", "emergency_contact", 20), NOW)
    assert c.state == state
    assert c.responder_flag is True


def test_need_help_from_verified_stays_verified_and_flags():
    c = transition(transition(mk(), Timer("call_driver", 0), NOW), Timer("dispatch_drone", 18), NOW)
    c = transition(c, DroneArrived(vision(), 1, 20), NOW)
    c = transition(c, Reply("need_help", "driver", 22), NOW)
    assert c.state == "verified"
    assert c.responder_flag is True


# ---------- resolved / ordering ----------


@pytest.mark.parametrize(
    "event",
    [
        Timer("call_driver", 1),
        Timer("contact_family", 1),
        Timer("dispatch_drone", 1),
        DroneArrived(None, None, 1),
        Handoff(1),
        Reply("need_help", "driver", 1),
        Reply("safe", "driver", 1),
    ],
)
def test_resolved_ignores_everything(event):
    c = transition(mk(), Reply("safe", "driver", 3), NOW)
    assert c.state == "resolved"
    assert transition(c, event, NOW) == c


@pytest.mark.parametrize(
    "state,timer",
    [
        ("contacting_family", Timer("call_driver", 0)),
        ("drone_en_route", Timer("call_driver", 0)),
        ("drone_en_route", Timer("contact_family", 12)),
        ("calling", Timer("call_driver", 0)),
        ("monitoring", Timer("contact_family", 12)),
        ("contacting_family", Timer("contact_family", 12)),
    ],
)
def test_out_of_order_timers_ignored(state, timer):
    c = at(mk(), state)
    assert transition(c, timer, NOW) == c


def test_handed_state_never_downgraded_by_timers():
    c = transition(mk(), Handoff(1), NOW)
    for t in ("call_driver", "contact_family", "dispatch_drone"):
        assert transition(c, Timer(t, 9), NOW).state == "handed_to_responders"


def test_open_event_is_noop():
    c = mk()
    assert transition(c, Open(NOW, 0), NOW) == c


def test_transition_appends_timeline_entry_with_event_time():
    c = mk()
    c2 = transition(c, Timer("call_driver", 0), "2026-07-04T05:00:01+00:00")
    e = c2.timeline[-1]
    assert (e.ts, e.t_case_s, e.kind, e.text) == (
        "2026-07-04T05:00:01+00:00",
        0,
        "state",
        "Calling driver",
    )


# ---------- immutability ----------


def test_original_case_unchanged_after_transition():
    c = mk()
    snapshot = c.model_copy(deep=True)
    c2 = transition(c, Timer("call_driver", 0), NOW)
    assert c2 is not c
    assert c == snapshot
    assert c.state == "monitoring"
    assert len(c.timeline) == 1


def test_original_unchanged_through_full_flow():
    c = at(mk(), "drone_en_route")
    snapshot = c.model_copy(deep=True)
    transition(c, DroneArrived(vision(), 2, 30), NOW)
    transition(c, Reply("safe", "driver", 30), NOW)
    assert c == snapshot


def test_state_never_regresses_across_event_sequence():
    c = mk()
    events = [
        Timer("call_driver", 0),
        Timer("contact_family", 12),
        Timer("dispatch_drone", 18),
        Timer("call_driver", 19),
        Timer("contact_family", 20),
        DroneArrived(vision(), 1, 25),
        Timer("dispatch_drone", 26),
        Handoff(27),
        Timer("call_driver", 28),
    ]
    prev = 0
    for ev in events:
        c = transition(c, ev, NOW)
        idx = ORDER.index(c.state)
        assert idx >= prev
        prev = idx


# ---------- due_timers ----------


def test_due_timers_demo_profile():
    c = mk()
    assert due_timers(c, 0, frozenset(), DEMO) == ["call_driver"]
    assert due_timers(c, 11.9, frozenset(), DEMO) == ["call_driver"]
    assert due_timers(c, 12, frozenset(), DEMO) == ["call_driver", "contact_family"]
    assert due_timers(c, 18, frozenset(), DEMO) == [
        "call_driver",
        "contact_family",
        "dispatch_drone",
    ]


def test_due_timers_excludes_fired():
    c = mk()
    assert due_timers(c, 18, frozenset({"call_driver", "contact_family"}), DEMO) == [
        "dispatch_drone"
    ]
    assert due_timers(c, 18, frozenset(DEMO), DEMO) == []


def test_due_timers_none_when_resolved():
    c = transition(mk(), Reply("safe", "driver", 3), NOW)
    assert due_timers(c, 100, frozenset(), DEMO) == []


def test_due_timers_normal_profile():
    c = mk()
    normal = {"call_driver": 0, "contact_family": 120, "dispatch_drone": 180}
    assert due_timers(c, 119.9, frozenset(), normal) == ["call_driver"]
    assert due_timers(c, 120, frozenset({"call_driver"}), normal) == ["contact_family"]
