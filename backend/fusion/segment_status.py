"""Belief: probability a road segment is flooded, from evidence (overview.md 6.3) with decay (6.4).

Kept simple and explainable: a prior, additive supporting evidence (capped below "confirmed"),
and overrides for direct evidence. Weights live in config/fusion.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.config import fusion_settings

Status = Literal["open", "unknown", "likely_flooded", "confirmed_flooded"]


@dataclass(frozen=True)
class DroneObs:
    wet: bool
    age_s: float


@dataclass(frozen=True)
class Signals:
    floodable: bool
    in_warning: bool
    gauge_rising: bool = False        # nearest upstream *reporting* gauge rising fast
    model_above_road: bool = False    # gauge-interpolated stage is above this road
    heavy_rain: bool = False
    driver_signals: bool = False      # Drive Safe & Save stops / U-turns here (synthetic)
    closure: bool = False             # agency closure or USGS impact point exceeded
    drone: DroneObs | None = None
    gauges_rising: bool = False       # any gauge in the region rising: drone evidence ages faster


def _indirect(s: Signals) -> float:
    f = fusion_settings()["fusion"]
    if not (s.floodable and s.in_warning):
        return f["prior_outside"]
    p = f["prior_in_warning"]
    p += f["add_gauge_rising"] * s.gauge_rising + f["add_model_above_road"] * s.model_above_road
    p += f["add_heavy_rain"] * s.heavy_rain + f["add_driver_signals"] * s.driver_signals
    return min(p, f["indirect_cap"])


def p_flooded(s: Signals) -> float:
    f = fusion_settings()["fusion"]
    if s.closure:
        return f["drone_wet"]
    prior = _indirect(s)
    if s.drone is None:
        return prior
    if s.drone.wet:  # stays confirmed until new direct evidence says otherwise
        return f["drone_wet"]
    half_life = f["decay_half_life_s"]["rising" if s.gauges_rising else "steady"]
    weight = 0.5 ** (max(0.0, s.drone.age_s) / half_life)
    return weight * f["drone_dry"] + (1 - weight) * prior


def status(p: float) -> Status:
    b = fusion_settings()["fusion"]["bands"]
    if p < b["open"]:
        return "open"
    if p < b["unknown"]:
        return "unknown"
    if p < b["likely"]:
        return "likely_flooded"
    return "confirmed_flooded"
