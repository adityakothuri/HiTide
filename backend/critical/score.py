"""Critical-point priority (overview.md section 8.4). Pure and explainable: every factor is returned.

priority = dependency x vulnerability x p_weight x uncertainty x urgency

- dependency:    sum of households that rely on the point (1.0 unavoidable, 0.3 optional, 0.5 truck access)
- vulnerability: 1 + 0.5 older + 0.3 one-story/manufactured + 0.3 cars still home (household-weighted)
- p_weight:      0.5 + p          (lean toward points that are probably flooded)
- uncertainty:   4 p (1 - p)      (scaled Bernoulli variance: 1 at p = 0.5, 0 when we already know)
- urgency:       1.5 if the upstream gauge is rising fast or the forecast reaches the point within 60 min
See docs/drone-critical-points.md for why the product peaks at p ~ 0.61.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from app.config import fusion_settings

UseKind = Literal["unavoidable", "optional", "truck_access"]


@dataclass(frozen=True)
class NodeUse:
    node_id: str
    households: int
    kind: UseKind
    older_share: float = 0.0
    one_story_share: float = 0.0
    cars_home_share: float = 0.0


@dataclass(frozen=True)
class PointInput:
    point_id: str
    p: float
    uses: tuple[NodeUse, ...]
    urgent: bool


@dataclass(frozen=True)
class Breakdown:
    point_id: str
    p: float
    dependency: float
    vulnerability: float
    p_weight: float
    uncertainty: float
    urgency: float
    priority: float
    node_ids: tuple[str, ...]


def uncertainty(p: float) -> float:
    return 4.0 * p * (1.0 - p)


def _use_weight(kind: UseKind) -> float:
    w = fusion_settings()["priority"]
    return {"unavoidable": w["unavoidable_weight"], "optional": w["optional_weight"],
            "truck_access": w["truck_access_weight"]}[kind]


def _vulnerability(uses: tuple[NodeUse, ...]) -> float:
    total = sum(u.households for u in uses)
    if total == 0:
        return 1.0
    w = fusion_settings()["priority"]["vulnerability"]
    def share(attr: str) -> float:
        return sum(getattr(u, attr) * u.households for u in uses) / total
    return 1.0 + w["older"] * share("older_share") + w["one_story"] * share("one_story_share") \
        + w["cars_home"] * share("cars_home_share")


def priority(point: PointInput) -> Breakdown:
    if not 0.0 <= point.p <= 1.0:
        raise ValueError(f"p_flooded must be in [0, 1], got {point.p}")
    dependency = sum(u.households * _use_weight(u.kind) for u in point.uses)
    vulnerability = _vulnerability(point.uses)
    p_weight = 0.5 + point.p
    unc = uncertainty(point.p)
    urgency = fusion_settings()["priority"]["urgency_rising"] if point.urgent else 1.0
    return Breakdown(point.point_id, point.p, dependency, vulnerability, p_weight, unc, urgency,
                     dependency * vulnerability * p_weight * unc * urgency,
                     tuple(sorted({u.node_id for u in point.uses})))


def rank(points: Iterable[PointInput]) -> list[Breakdown]:
    """Highest priority first; points nobody depends on never enter the drone queue."""
    scored = [priority(p) for p in points if p.uses]
    return sorted(scored, key=lambda b: (-b.priority, b.point_id))
