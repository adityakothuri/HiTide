"""API contract shared with the frontend team. Mirror of docs/api-contract.md.

Every WebSocket message is a WsEvent envelope; `payload` shape depends on `type`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RoadStatusName = Literal["open", "caution", "closed", "float", "boat"]
Situation = Literal["parked", "planning", "driving", "stopped_in_water"]
CaseState = Literal[
    "monitoring",
    "calling",
    "contacting_family",
    "drone_en_route",
    "verified",
    "handed_to_responders",
    "resolved",
]
EventType = Literal[
    "snapshot",          # full StateSnapshot, sent once on connect
    "segments.update",   # SegmentsUpdate: only segments whose depth/status changed
    "drivers.update",    # DriversUpdate: positions of moving / changed drivers
    "alert",             # Alert: flash flood warning issued / cleared
    "outreach",          # OutreachEvent: every text / call / poll attempt
    "turn_around",       # TurnAround: driver view should speak + show full-screen alert
    "reroute",           # Reroute: new dry route for a driver
    "case.update",       # Case: full case object on every state change
    "drone.update",      # DroneState: position + ETA each tick
    "counters",          # Counters
    "demo.step",         # DemoStep: narration for the scripted demo
    "snapshot.created",  # VisionSnapshot: drone snapshot of a critical point (overview 9.5 + drone vision plan 8)
]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class LatLon(Frozen):
    lat: float
    lon: float


class SegmentState(Frozen):
    edge_id: str
    depth_in: float
    status: RoadStatusName


class SegmentsUpdate(Frozen):
    t_sim_s: float
    river_wse_m: float
    segments: list[SegmentState]


class DriverPublic(Frozen):
    """What the ops map sees. Age/vehicle only drive outreach order; shown on the case card, not the map."""

    id: str
    name: str
    lat: float
    lon: float
    heading_deg: float = 0.0
    situation: Situation
    is_demo: bool = False
    urgency: float = 0.0


class DriversUpdate(Frozen):
    drivers: list[DriverPublic]


class Alert(Frozen):
    id: str
    event: str                 # e.g. "Flash Flood Warning"
    headline: str
    active: bool
    simulated: bool
    polygon: dict[str, Any] | None = None  # GeoJSON geometry


class OutreachEvent(Frozen):
    id: str
    ts: str                    # ISO8601
    driver_id: str
    recipient: Literal["driver", "parent", "emergency_contact"]
    channel: Literal["text", "poll", "voice", "tts_in_app"]
    body: str
    mode: Literal["mock", "photon"]
    status: Literal["queued", "sent", "delivered", "read", "failed", "blocked", "suppressed"]  # suppressed: live mode, number not allowlisted
    case_id: str | None = None
    provider: Literal["stable", "photon2"] | None = None  # set only for live sends
    call_id: str | None = None  # ElevenLabs conversation_id for voice calls


class TurnAround(Frozen):
    driver_id: str
    message: str               # "Flooded road ahead. Turn around."
    hazard_edge_id: str
    hazard_depth_in: float
    distance_m: float


class Reroute(Frozen):
    driver_id: str
    reason: str
    route: dict[str, Any]      # GeoJSON LineString
    blocked_edge_ids: list[str]
    distance_m: float


class TimelineEntry(Frozen):
    ts: str
    t_case_s: float
    kind: str                  # "state", "outreach", "reply", "flag", "drone", "vision"
    text: str


class VisionResult(Frozen):
    image_url: str             # served from /static/drone/...
    annotated_url: str
    car_detected: bool
    water_level: Literal["none", "wheels", "doors", "windows", "roof"]
    water_level_source: Literal["manual_label", "rule"]
    people: list[dict[str, Any]]  # [{placement: on_roof|in_water|on_shore|inside_unknown, box:[x1,y1,x2,y2], conf}]
    night_mode: bool
    thermal_simulated: bool
    recommendation: Literal["truck_route_available", "boat_required"]


class ResponderView(Frozen):
    """Only what responders need (Privacy and Consent)."""

    location: LatLon
    people_count: int | None
    water_depth_in: float


class Case(Frozen):
    id: str
    driver_id: str
    driver_name: str
    state: CaseState
    urgency: float
    urgency_reasons: list[str]
    responder_flag: bool
    location: LatLon
    depth_in: float
    opened_at: str
    timeline: list[TimelineEntry]
    vision: VisionResult | None = None
    responder_view: ResponderView


class DroneState(Frozen):
    id: str
    case_id: str
    lat: float
    lon: float
    eta_s: float
    status: Literal["launching", "en_route", "on_scene", "returning"]


class Counters(Frozen):
    drivers_warned: int = 0
    drivers_rerouted: int = 0
    cars_stopped_in_water: int = 0
    people_verified: int = 0
    est_claims_avoided_usd: int = 0


class DemoStep(Frozen):
    step: int
    title: str
    detail: str


class StateSnapshot(Frozen):
    t_sim_s: float
    river_wse_m: float
    alert: Alert | None
    segments: list[SegmentState]   # only non-open segments, to keep it small
    drivers: list[DriverPublic]
    cases: list[Case]
    drones: list[DroneState]
    counters: Counters


class WsEvent(Frozen):
    type: EventType
    seq: int
    ts: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ReplyIn(BaseModel):
    reply: Literal["safe", "need_help"]


class DroneCommandIn(BaseModel):
    command: Literal["speak", "drop_jacket", "return"]
