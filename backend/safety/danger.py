"""Danger = hazard at the user's position x the user's vulnerability x what they are doing (motion).

Rules (all tested):
- The hazard level comes from evidence only (safety/hazard.py).
- Stopped in water: stopped >= motion.stop_seconds on a road with >= caution depth (or a confirmed-flooded
  crossing on your road) is CRITICAL.
- High vulnerability (or a teen at the wheel) raises the level one step, never above CRITICAL. NONE stays NONE:
  vulnerability never invents a hazard, and nothing here ever lowers a level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from app.config import safety_settings
from safety.context import SafetyContext
from safety.hazard import WET_STATUSES, LocationHazard, Locator, assess, classify_hazard
from safety.levels import Level
from safety.motion import MotionState
from safety.vulnerability import Vulnerability, vulnerability


@dataclass(frozen=True)
class DangerAssessment:
    user_id: str
    level: Level
    hazard_level: Level
    reasons: tuple[str, ...]
    advice: str                      # turn_around | do_not_drive | move_to_high_ground | stay_on_high_ground | be_ready | none
    hazard: LocationHazard
    vulnerability: Vulnerability
    motion: MotionState
    stopped_in_water: bool = False
    location_stale: bool = False
    assessed_at: float = 0.0
    bumped: bool = False
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def confidence(self) -> str:
        return self.hazard.confidence

    def public(self) -> dict[str, Any]:
        return {"user_id": self.user_id, "level": self.level.label, "hazard_level": self.hazard_level.label,
                "bumped_for_vulnerability": self.bumped, "reasons": list(self.reasons), "advice": self.advice,
                "confidence": self.confidence, "stopped_in_water": self.stopped_in_water,
                "location_stale": self.location_stale,
                "assessed_at": datetime.fromtimestamp(self.assessed_at, tz=timezone.utc).isoformat(),
                "location": self.motion.public(), "hazard": self.hazard.public(),
                "vulnerability": self.vulnerability.public()}


def _stopped_in_water(h: LocationHazard, m: MotionState, now: float, cfg: Mapping[str, Any]) -> bool:
    if m.state != "stopped" or m.stopped_for(now) < float(cfg["motion"]["stop_seconds"]):
        return False
    wet_road = h.depth_in is not None and h.depth_in >= float(cfg["depth_in"]["caution"])
    wp = h.worst_point
    on_flooded_crossing = bool(wp and wp.on_my_road and wp.status in WET_STATUSES
                               and wp.distance_m <= float(cfg["snap"]["crossing_on_m"]))
    return wet_road or on_flooded_crossing


def _advice(level: Level, h: LocationHazard, driving: bool, cfg: Mapping[str, Any]) -> str:
    if level == Level.NONE:
        return "none"
    if driving and h.ahead:
        return "turn_around"
    if h.route:
        return "do_not_drive"
    if level <= Level.WATCH:
        return "be_ready"
    hag = h.height_above_water_m
    high = h.far_from_water or (hag is not None and hag >= float(cfg["high_ground_m"]))
    return "stay_on_high_ground" if high and not driving else "move_to_high_ground"


def assess_user(loc: Locator, ctx: SafetyContext, user_id: str, profile: Mapping[str, Any] | None, age: int | None,
                motion: MotionState, now: float, route_edges: tuple[int, ...] = (), pinged: bool = False,
                cfg: Mapping[str, Any] | None = None) -> DangerAssessment:
    c: Mapping[str, Any] = cfg if cfg is not None else safety_settings()
    when = datetime.fromtimestamp(now, tz=timezone.utc)
    vuln = vulnerability(profile, age, when, loc.region.cfg.get("timezone", "America/Chicago"), c["vulnerability"])
    driving = motion.state == "driving"
    h = assess(loc, ctx, motion.lat, motion.lon, motion.heading_deg, driving, () if driving else route_edges)
    hz, reasons = classify_hazard(h, vuln.stall_depth_in, driving, c)
    level, why = hz, list(reasons)
    stuck = _stopped_in_water(h, motion, now, c)
    if stuck:
        level = Level.CRITICAL
        why.insert(0, f"Your vehicle has been stopped in water on {h.road_name or 'the road'} "
                      f"for {motion.stopped_for(now):.0f} s")
    bumped = False
    if level > Level.NONE and (vuln.high or (vuln.is_teen and driving)):
        new = level.bump()
        bumped = new > level
        if bumped:
            who = ", ".join(vuln.reasons[:2]) or "high vulnerability"
            why.append(f"Raised one level: {who}")
        level = new
    stale = (pinged and level >= Level.WARNING
             and now - motion.ts >= float(c["motion"]["stale_location_s"]))
    if stale:
        why.append(f"No location update for {(now - motion.ts) / 60:.0f} min")
    return DangerAssessment(user_id, level, hz, tuple(dict.fromkeys(why)), _advice(level, h, driving, c), h, vuln,
                            motion, stuck, stale, now, bumped)
