"""Driver urgency score: orders outreach only (never pricing). Weights in config/weights.yaml.

urgency = sum(weight_i * factor_i), each factor normalized to [0, 1]. See vault/Modules/Risk Scoring.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.config import settings

RISE_SATURATION_IN_PER_MIN = 3.0
AGE_RAMP_YEARS = 15
SITUATION_TEXT = {
    "planning": "planning a trip through flooding",
    "driving_toward": "driving toward a flooded road",
    "stopped_in_water": "stopped in floodwater",
}


@dataclass(frozen=True)
class RiskInput:
    depth_in: float
    rise_in_per_min: float
    hour: int
    age: int
    vehicle_type: str
    situation: str  # planning | driving_toward | stopped_in_water


@dataclass(frozen=True)
class RiskScore:
    value: float
    reasons: tuple[str, ...]
    high_risk: bool
    notify_parent: bool
    factors: Mapping[str, float]


def _is_night(hour: int, night: list[int]) -> bool:
    start, end = night
    return hour >= start or hour < end


def _age_factor(age: int, cfg: Mapping[str, Any]) -> float:
    if age >= cfg["older_age"]:
        return 0.6 + 0.4 * min(1.0, (age - cfg["older_age"]) / AGE_RAMP_YEARS)
    if age <= cfg["teen_max_age"]:
        return 0.5
    return 0.0


def factors(inp: RiskInput, cfg: Mapping[str, Any], boat_in: float) -> dict[str, float]:
    return {
        "depth": min(1.0, max(0.0, inp.depth_in) / boat_in),
        "rise": min(1.0, max(0.0, inp.rise_in_per_min) / RISE_SATURATION_IN_PER_MIN),
        "night": 1.0 if _is_night(inp.hour, cfg["night_hours"]) else 0.0,
        "age": _age_factor(inp.age, cfg),
        "vehicle": float(cfg["vehicle_levels"].get(inp.vehicle_type, 0.5)),
        "situation": float(cfg["situation_levels"].get(inp.situation, 0.2)),
    }


def _reasons(inp: RiskInput, f: Mapping[str, float], cfg: Mapping[str, Any]) -> tuple[str, ...]:
    out = [SITUATION_TEXT.get(inp.situation, inp.situation)]
    if inp.depth_in > 0:
        out.append(f"{inp.depth_in:.0f} in of water")
    if inp.rise_in_per_min > 0.1:
        out.append(f"water rising {inp.rise_in_per_min:.1f} in/min")
    if f["night"]:
        out.append("night")
    if inp.age >= cfg["older_age"]:
        out.append(f"age {inp.age}")
    elif inp.age <= cfg["teen_max_age"]:
        out.append(f"teen driver (age {inp.age})")
    if f["vehicle"] >= 0.6:
        out.append(f"low-clearance vehicle ({inp.vehicle_type})")
    return tuple(out)


def score(inp: RiskInput, cfg: Mapping[str, Any] | None = None) -> RiskScore:
    conf = settings()
    risk_cfg = cfg or conf["risk"]
    f = factors(inp, risk_cfg, float(conf["road_status_in"]["boat"]))
    value = sum(risk_cfg["weights"][k] * v for k, v in f.items())
    value = round(min(1.0, max(0.0, value)), 3)
    return RiskScore(
        value=value,
        reasons=_reasons(inp, f, risk_cfg),
        high_risk=value >= risk_cfg["high_risk_threshold"],
        notify_parent=inp.age <= risk_cfg["teen_max_age"],
        factors=f,
    )
