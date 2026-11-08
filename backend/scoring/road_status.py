"""Road status from water depth over the road (NWS Turn Around Don't Drown)."""

from __future__ import annotations

from enum import Enum
from typing import Mapping

from app.config import settings


class RoadStatus(str, Enum):
    OPEN = "open"
    CAUTION = "caution"
    CLOSED = "closed"
    FLOAT = "float"
    BOAT = "boat"

    @property
    def passable_for_cars(self) -> bool:
        return self in (RoadStatus.OPEN, RoadStatus.CAUTION)

    @property
    def passable_for_trucks(self) -> bool:
        return self is not RoadStatus.BOAT


def classify(depth_in: float, thresholds: Mapping[str, float] | None = None) -> RoadStatus:
    t = thresholds or settings()["road_status_in"]
    if depth_in >= t["boat"]:
        return RoadStatus.BOAT
    if depth_in >= t["float"]:
        return RoadStatus.FLOAT
    if depth_in >= t["closed"]:
        return RoadStatus.CLOSED
    if depth_in >= t["caution"]:
        return RoadStatus.CAUTION
    return RoadStatus.OPEN
