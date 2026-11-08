"""Area (community) risk score, 0-100, so every area can be ranked and people moved from low to high ground.

risk = 100 x (w_access x access + w_water x water + w_ground x ground + w_vuln x vulnerability)
  access         cut_off 1.0 | at_risk 0.7 | partially_cut_off 0.4 | ok 0     (can they still get out?)
  water          max(p_flooded over the area's exit points, 1.0 if its own roads have water)
  ground         1 - height_above_nearest_waterway / 15 m, clipped to [0, 1]  (how low the area sits)
  vulnerability  (0.5 older + 0.3 one-story/manufactured + 0.3 cars still home) / 1.1
Weights and bands live in config/fusion.yaml (area_risk). Every factor's contribution is returned so the
console can say *why* an area is high risk. Like all scores here it orders outreach, never pricing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from app.config import fusion_settings

Band = Literal["low", "moderate", "high", "severe"]
Ground = Literal["low", "mid", "high"]


@dataclass(frozen=True)
class AreaInputs:
    hand_m: float              # height above the nearest named waterway (inf if none within reach)
    status: str                # ok | at_risk | partially_cut_off | cut_off
    max_exit_p: float          # worst p_flooded among the area's exit points
    own_road_flooded: bool
    older_share: float
    one_story_share: float
    cars_home_share: float


@dataclass(frozen=True)
class AreaRisk:
    score: float
    band: Band
    ground: Ground
    factors: dict[str, float]  # each factor's contribution to the score, in points


def _cfg() -> dict:
    return fusion_settings()["area_risk"]


def ground_label(hand_m: float) -> Ground:
    c = _cfg()
    if hand_m < c["low_ground_m"]:
        return "low"
    return "high" if hand_m >= c["high_ground_m"] else "mid"


def _band(score: float) -> Band:
    b = _cfg()["bands"]
    if score < b["low"]:
        return "low"
    if score < b["moderate"]:
        return "moderate"
    return "high" if score < b["high"] else "severe"


def area_risk(a: AreaInputs) -> AreaRisk:
    c, w = _cfg(), _cfg()["weights"]
    vw = fusion_settings()["priority"]["vulnerability"]
    access = c["access"].get(a.status, 0.0)
    water = 1.0 if a.own_road_flooded else min(1.0, max(0.0, a.max_exit_p))
    ground = 0.0 if math.isinf(a.hand_m) else min(1.0, max(0.0, 1.0 - a.hand_m / c["ground_full_m"]))
    vuln_max = vw["older"] + vw["one_story"] + vw["cars_home"]
    vulnerability = (vw["older"] * a.older_share + vw["one_story"] * a.one_story_share
                     + vw["cars_home"] * a.cars_home_share) / vuln_max
    factors = {"access": 100 * w["access"] * access, "water": 100 * w["water"] * water,
               "ground": 100 * w["ground"] * ground, "vulnerability": 100 * w["vulnerability"] * vulnerability}
    score = round(sum(factors.values()), 1)
    return AreaRisk(score, _band(score), ground_label(a.hand_m), {k: round(v, 1) for k, v in factors.items()})
