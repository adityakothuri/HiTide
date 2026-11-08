"""Location pings -> motion state. Pure functions over frozen dataclasses.

parked   not moving and hasn't driven recently (home, work)
driving  speed >= driving_mps
stopped  not moving, but drove within recent_drive_s (pulled over, stalled, stuck in traffic... or in water)

GPS jitter: a move smaller than max(jitter_floor_m, reported accuracy) counts as no move, so a parked phone
doesn't flicker into "driving". A reported speed (from the phone) beats one derived from two pings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Literal, Mapping

from app.config import safety_settings

State = Literal["parked", "driving", "stopped"]
EARTH_M = 6_371_000.0


@dataclass(frozen=True)
class Ping:
    lat: float
    lon: float
    ts: float                         # epoch seconds (sim time in replay)
    speed_mps: float | None = None
    heading_deg: float | None = None
    accuracy_m: float | None = None


@dataclass(frozen=True)
class MotionState:
    lat: float
    lon: float
    ts: float                          # last ping time
    state: State = "parked"
    speed_mps: float = 0.0
    heading_deg: float | None = None
    still_since: float | None = None   # when it last stopped moving
    last_moving_ts: float | None = None

    def stopped_for(self, now: float) -> float:
        return 0.0 if self.still_since is None or self.state == "driving" else max(0.0, now - self.still_since)

    def public(self) -> dict[str, Any]:
        return {"lat": self.lat, "lon": self.lon, "ts": self.ts, "state": self.state,
                "speed_mps": round(self.speed_mps, 1), "heading_deg": self.heading_deg}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_M * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(x, y)) % 360.0


def initial(ping: Ping) -> MotionState:
    moving = (ping.speed_mps or 0.0) >= safety_settings()["motion"]["driving_mps"]
    return MotionState(ping.lat, ping.lon, ping.ts, "driving" if moving else "parked", ping.speed_mps or 0.0,
                       ping.heading_deg, None if moving else ping.ts, ping.ts if moving else None)


def update(prev: MotionState | None, ping: Ping, cfg: Mapping[str, Any] | None = None) -> MotionState:
    """Fold one ping into the state. Out-of-order or duplicate pings (ts <= prev.ts) are ignored."""
    c: Mapping[str, Any] = cfg if cfg is not None else safety_settings()["motion"]
    if prev is None:
        return initial(ping)
    if ping.ts <= prev.ts:
        return prev
    dt = ping.ts - prev.ts
    dist = haversine_m(prev.lat, prev.lon, ping.lat, ping.lon)
    noise = max(float(c["jitter_floor_m"]), ping.accuracy_m or 0.0)
    if ping.speed_mps is not None:
        speed = max(0.0, ping.speed_mps)
    else:
        speed = 0.0 if dist <= noise else dist / dt
    heading = ping.heading_deg
    if heading is None and dist > noise:
        heading = bearing_deg(prev.lat, prev.lon, ping.lat, ping.lon)
    if heading is None:
        heading = prev.heading_deg
    if speed >= float(c["driving_mps"]):
        return MotionState(ping.lat, ping.lon, ping.ts, "driving", speed, heading, None, ping.ts)
    still_since = prev.still_since if prev.state != "driving" and prev.still_since is not None else ping.ts
    recent = prev.last_moving_ts is not None and ping.ts - prev.last_moving_ts <= float(c["recent_drive_s"])
    state: State = "stopped" if recent else "parked"
    # A stationary phone keeps its first fix (jitter must not walk the position).
    lat, lon = (prev.lat, prev.lon) if dist <= noise else (ping.lat, ping.lon)
    return replace(prev, lat=lat, lon=lon, ts=ping.ts, state=state, speed_mps=speed, heading_deg=heading,
                   still_since=still_since)


def at_rest(lat: float, lon: float, ts: float) -> MotionState:
    """A registered home location with no pings yet."""
    return MotionState(lat, lon, ts, "parked", 0.0, None, ts, None)
