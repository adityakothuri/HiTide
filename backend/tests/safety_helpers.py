"""Builders for synthetic safety objects (no region load)."""

from __future__ import annotations

from datetime import datetime, timezone

from safety.danger import DangerAssessment
from safety.hazard import LocationHazard, NearbyPoint
from safety.levels import Level
from safety.motion import MotionState
from safety.vulnerability import Vulnerability, vulnerability

NOON = datetime(2025, 7, 4, 17, 0, tzinfo=timezone.utc)      # 12:00 CDT
MIDNIGHT = datetime(2025, 7, 4, 5, 0, tzinfo=timezone.utc)   # 00:00 CDT
TZ = "America/Chicago"


def hazard(**kw) -> LocationHazard:
    base = dict(lat=30.05, lon=-99.2, coverage="region", height_above_water_m=8.0)
    return LocationHazard(**{**base, **kw})


def point(status: str = "likely_flooded", distance_m: float = 200.0, on_my_road: bool = False) -> NearbyPoint:
    return NearbyPoint("cp-1", "Low Water Rd", "low_water", "Johnson Creek", status, 0.6, distance_m, on_my_road)


def vuln(score: float = 0.1, band: str = "low", stall: float = 12.0, needs: bool = False, teen: bool = False,
         channel: str = "sms", no_voice: bool = False, language: str = "en") -> Vulnerability:
    return Vulnerability(score, band, stall, needs, teen, False, channel, no_voice, language, (), {})


def plain_vuln() -> Vulnerability:
    return vulnerability({"policy": {"stall_depth_in": 18}}, 40, NOON, TZ)


def motion(state: str = "parked", ts: float = 0.0) -> MotionState:
    return MotionState(30.05, -99.2, ts, state)  # type: ignore[arg-type]


def assessment(level: Level, v: Vulnerability | None = None, state: str = "parked", advice: str = "move_to_high_ground",
               reasons: tuple[str, ...] = ("Water near you",), stale: bool = False, now: float = 0.0) -> DangerAssessment:
    return DangerAssessment("u1", level, level, reasons, advice, hazard(), v or vuln(), motion(state, now),
                            location_stale=stale, assessed_at=now)
