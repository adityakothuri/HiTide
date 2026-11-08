"""Per-user danger API (docs/api-contract.md "Per-user danger"). Thin: validation here, behaviour in safety/."""

from __future__ import annotations

import asyncio
import hmac
import os
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.hill_runtime import get_hill
from app.security import require_trusted_origin
from safety.levels import Level
from safety.monitor import SafetyMonitor, public_assessment
from safety.motion import Ping
from safety.users import E164, SafetyUser
from sim.profiles import STALL_DEPTH_IN

router = APIRouter()
ID_PATTERN = r"^[A-Za-z0-9_-]{3,40}$"
KNOWN_NEEDS = {"mobility_assist", "wheelchair_user", "powered_medical_equipment", "cognitive_support", "pregnant",
               "hearing_loss", "low_vision"}
MAX_PAST_S = 3600.0
MAX_ROUTE_POINTS = 2000


class LocationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    speed_mps: float | None = Field(default=None, ge=0, le=90)
    heading_deg: float | None = Field(default=None, ge=0, lt=360)
    accuracy_m: float | None = Field(default=None, ge=0, le=5000)
    ts: float | None = Field(default=None, description="epoch seconds; default now (replay: always the sim clock)")


class RouteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    points: list[tuple[float, float]] = Field(min_length=2, max_length=MAX_ROUTE_POINTS, description="[[lat, lon], ...]")

    @field_validator("points")
    @classmethod
    def _in_range(cls, v: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if any(not (-90 <= la <= 90 and -180 <= lo <= 180) for la, lo in v):
            raise ValueError("lat/lon out of range")
        return v


class ReplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reply: Literal["safe", "need_help"]
    by: Literal["driver", "emergency_contact", "parent"] = "driver"


class EnrollIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=80, pattern=r"^[^\W\d_][\w .'-]*$")
    phone: str = Field(pattern=E164.pattern, description="+E.164; stored only in the gitignored registry")
    age: int | None = Field(default=None, ge=13, le=110)
    vehicle_type: Literal["compact", "sedan", "ev", "minivan", "suv", "truck"] = "sedan"
    home_lat: float = Field(ge=-90, le=90)
    home_lon: float = Field(ge=-180, le=180)
    contact_name: str | None = Field(default=None, max_length=80, pattern=r"^[^\W\d_][\w .'-]*$")
    contact_phone: str | None = Field(default=None, pattern=E164.pattern)
    needs: list[str] = Field(default_factory=list, max_length=8)
    language: Literal["en", "es"] = "en"
    preferred_channel: Literal["sms", "voice", "app"] = "sms"
    consent_flood_alerts: bool

    @field_validator("needs")
    @classmethod
    def _known(cls, v: list[str]) -> list[str]:
        bad = sorted(set(v) - KNOWN_NEEDS)
        if bad:
            raise ValueError(f"unknown needs {bad}; allowed {sorted(KNOWN_NEEDS)}")
        return v

    @field_validator("consent_flood_alerts")
    @classmethod
    def _must_consent(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("flood alerts need explicit consent")
        return v


async def require_api_key(request: Request) -> None:
    """SAFETY_API_KEY set -> enroll and reply need X-Safety-Key (the origin guard alone lets any non-browser client in)."""
    key = os.environ.get("SAFETY_API_KEY", "")
    if key and not hmac.compare_digest(request.headers.get("x-safety-key", ""), key):
        raise HTTPException(status_code=401, detail="missing or wrong X-Safety-Key")


async def monitor(request: Request) -> SafetyMonitor:
    hill = await get_hill(request.app)
    if hill.safety is None:
        raise HTTPException(status_code=503, detail="safety monitor not available")
    return hill.safety


def _user_or_404(m: SafetyMonitor, uid: str) -> SafetyUser:
    u = m.users.get(uid)
    if u is None:
        raise HTTPException(status_code=404, detail="unknown user")
    return u


def _with_response(m: SafetyMonitor, uid: str, body: dict) -> dict:
    r = m.response(uid)
    return {**body, "response": r.public() if r else None}


@router.get("/api/safety/summary")
async def summary(m: SafetyMonitor = Depends(monitor)) -> dict:
    ctx = m.ctx
    return {"mode": ctx.mode, "ready": ctx.ready, "users": len(m.users), "levels": m.counts(),
            "degraded_sources": list(ctx.degraded_sources()),
            "sources": {k: v.public() for k, v in ctx.sources.items()}}


@router.get("/api/users")
async def list_users(m: SafetyMonitor = Depends(monitor), limit: int = Query(200, ge=1, le=2000),
                     offset: int = Query(0, ge=0)) -> dict:
    users = sorted(m.users.all(), key=lambda u: u.id)
    return {"total": len(users), "users": [u.public() for u in users[offset:offset + limit]]}


@router.post("/api/users", status_code=201, dependencies=[Depends(require_trusted_origin), Depends(require_api_key)])
async def enroll(body: EnrollIn, m: SafetyMonitor = Depends(monitor)) -> dict:
    profile = {"version": 1, "simulated": False,
               "consent": {"flood_alerts": True, "share_location_on_escalation": True, "drone_check": False},
               "policy": {"stall_depth_in": STALL_DEPTH_IN[body.vehicle_type], "preferred_channel": body.preferred_channel,
                          "language": body.language},
               "needs": body.needs, "household": {}}
    user = SafetyUser(body.id, body.name, body.age, body.phone, body.home_lat, body.home_lon, body.contact_name,
                      body.contact_phone, None, profile, simulated=False, tags=("enrolled",))
    try:
        await asyncio.to_thread(m.users.enroll, user)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OverflowError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return user.public()


@router.get("/api/users/at-risk")
async def at_risk(m: SafetyMonitor = Depends(monitor), min_level: str = Query("warning"),
                  limit: int = Query(200, ge=1, le=2000)) -> dict:
    try:
        lv = Level.parse(min_level)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    rows = m.at_risk(lv)
    return {"mode": m.ctx.mode, "total": len(rows),
            "users": [_with_response(m, a.user_id, public_assessment(m.users.get(a.user_id), a)) for a in rows[:limit]]}


@router.get("/api/users/{uid}/danger")
async def danger(uid: str, m: SafetyMonitor = Depends(monitor)) -> dict:
    _user_or_404(m, uid)
    a = await asyncio.to_thread(m.assessment, uid)
    if a is None:
        raise HTTPException(status_code=409, detail="no flood picture yet: start the replay or live mode")
    return _with_response(m, uid, public_assessment(_user_or_404(m, uid), a))


@router.post("/api/users/{uid}/location", dependencies=[Depends(require_trusted_origin)])
async def location(uid: str, body: LocationIn, m: SafetyMonitor = Depends(monitor)) -> dict:
    u = _user_or_404(m, uid)
    if not m.ctx.ready:
        raise HTTPException(status_code=409, detail="no flood picture yet: start the replay or live mode")
    now = time.time()
    ts = body.ts if body.ts is not None else now
    if m.ctx.mode == "live" and ts > now + float(m.cfg["motion"]["max_future_skew_s"]):
        raise HTTPException(status_code=422, detail="ts is in the future")
    if m.ctx.mode == "live" and ts < now - MAX_PAST_S:
        raise HTTPException(status_code=422, detail="ts is more than an hour old")
    # A phone clock running ahead must not freeze the user (later pings with smaller ts would be ignored).
    ping = Ping(body.lat, body.lon, min(ts, now), body.speed_mps, body.heading_deg, body.accuracy_m)
    d = await asyncio.to_thread(m.ping, uid, ping)
    await m.dispatch([d])
    return _with_response(m, u.id, {**public_assessment(u, d.assessment), "actions": [x.public() for x in d.actions]})


@router.post("/api/users/{uid}/route", dependencies=[Depends(require_trusted_origin)])
async def route(uid: str, body: RouteIn, m: SafetyMonitor = Depends(monitor)) -> dict:
    _user_or_404(m, uid)
    edges = await asyncio.to_thread(m.set_route, uid, [tuple(p) for p in body.points])
    return {"user_id": uid, "edges_matched": len(edges)}


@router.post("/api/users/{uid}/reply", dependencies=[Depends(require_trusted_origin), Depends(require_api_key)])
async def reply(uid: str, body: ReplyIn, m: SafetyMonitor = Depends(monitor)) -> dict:
    u = _user_or_404(m, uid)
    acts = await asyncio.to_thread(m.reply, uid, body.reply, body.by)
    await m.dispatch_actions(u, acts)
    r = m.response(uid)
    return {"user_id": uid, "reply": body.reply, "response": r.public() if r else None}
