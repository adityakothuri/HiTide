"""Baseline flood vulnerability from a simulated driver profile. Design: docs/driver-profile.md.

value = sum(weight_i * factor_i) with weights summing to 1, each factor normalized to [0, 1].
Protection only: this orders outreach and never feeds pricing, underwriting, or claims. It only
uses fields the live urgency score does not already count (needs, new-to-area, distraction,
live signals live in scoring/risk.py), so nothing is counted twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.config import settings

CROSSING_TRIPS_SATURATION = 14       # trips/week across low-lying crossings that counts as "always"
NIGHT_SHARE_SATURATION = 0.5
SPEEDING_SATURATION_PER_100MI = 3.0
SCORE_14D_GOOD = 90                   # 14-day DSS score at or above this adds nothing
SCORE_14D_SPAN = 30                  # a score of 60 or lower saturates
NEW_DRIVER_YEARS = 3
MISSED_CHECKIN_DAYS = 2
PASSENGER_STEP = 0.5
REASON_MIN_FACTOR = 0.5

REASON_TEXT = {
    "crossing_exposure": "drives a low-lying crossing often",
    "night_driving": "drives often at night",
    "past_flood": "past flood claim",
    "behavior": "risky driving pattern (Drive Safe & Save)",
    "inexperience": "new driver",
    "home_exposure": "lives in a manufactured home",
    "reachability": "app check-in missed",
}


@dataclass(frozen=True)
class ProfileRisk:
    value: float
    reasons: tuple[str, ...]
    factors: Mapping[str, float]


def _section(profile: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    val = profile.get(key)
    return val if isinstance(val, Mapping) else {}


def _num(m: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    val = m.get(key)
    return float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else default


def _clamp(x: float) -> float:
    return min(1.0, max(0.0, x))


def _crossing_exposure(derived: Mapping[str, Any]) -> float:
    crossings = derived.get("frequent_crossings") or []
    trips = sum(_num(c, "trips_per_week") for c in crossings if isinstance(c, Mapping))
    return _clamp(trips / CROSSING_TRIPS_SATURATION)


def _behavior(dss: Mapping[str, Any], derived: Mapping[str, Any]) -> float:
    speeding = _num(derived, "speeding_per_100mi") / SPEEDING_SATURATION_PER_100MI
    score_14d = _num(dss, "score_14d", SCORE_14D_GOOD)
    return _clamp(max(speeding, (SCORE_14D_GOOD - score_14d) / SCORE_14D_SPAN))


def _inexperience(dss: Mapping[str, Any], policy: Mapping[str, Any]) -> float:
    years = policy.get("years_licensed")
    new = isinstance(years, (int, float)) and not isinstance(years, bool) and years < NEW_DRIVER_YEARS
    return 1.0 if new or dss.get("steer_clear_enrolled") is True else 0.0


def _passengers(household: Mapping[str, Any]) -> float:
    kids = household.get("kids_often_aboard") is True or _num(household, "dependents_at_home") > 0
    pets = household.get("pets") is True
    return _clamp(PASSENGER_STEP * (kids + pets))


def _reachability(dss: Mapping[str, Any]) -> float:
    health = _section(dss, "app_health")
    if not health:
        return 0.0
    missed = _num(health, "last_daily_signal_days_ago") >= MISSED_CHECKIN_DAYS
    return 1.0 if missed or health.get("location_always") is False else 0.0


def profile_factors(profile: Mapping[str, Any]) -> dict[str, float]:
    dss, derived = _section(profile, "dss"), _section(profile, "derived")
    policy, household = _section(profile, "policy"), _section(profile, "household")
    claims = _section(profile, "claims")
    return {
        "crossing_exposure": _crossing_exposure(derived),
        "night_driving": _clamp(_num(derived, "night_driving_share") / NIGHT_SHARE_SATURATION),
        "past_flood": 1.0 if claims.get("past_flood_claims") else 0.0,
        "behavior": _behavior(dss, derived),
        "inexperience": _inexperience(dss, policy),
        "passengers": _passengers(household),
        "home_exposure": 1.0 if policy.get("home_type") == "manufactured" else 0.0,
        "reachability": _reachability(dss),
    }


def _reasons(f: Mapping[str, float], household: Mapping[str, Any]) -> tuple[str, ...]:
    out = [text for key, text in REASON_TEXT.items() if f[key] >= REASON_MIN_FACTOR]
    if household.get("kids_often_aboard") is True or _num(household, "dependents_at_home") > 0:
        out.append("kids or dependents often aboard")
    if household.get("pets") is True:
        out.append("pets aboard")
    return tuple(out)


def profile_vulnerability(profile: Mapping[str, Any] | None, cfg: Mapping[str, Any] | None = None) -> ProfileRisk:
    profile = profile if isinstance(profile, Mapping) else {}
    weights = (cfg or settings()["profile_risk"])["weights"]
    f = profile_factors(profile)
    value = round(_clamp(sum(weights[k] * v for k, v in f.items())), 3)
    return ProfileRisk(value=value, reasons=_reasons(f, _section(profile, "household")), factors=f)
