"""Pure route checks for Stage 1 (pre-trip) and Stage 2 (en-route lookahead)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from sim.drivers import Driver

BLOCKING = frozenset({"closed", "float", "boat"})
AT_RISK = frozenset({"caution"})


@dataclass(frozen=True)
class Hit:
    edge_id: str
    status: str


@dataclass(frozen=True)
class PretripWarning:
    driver_id: str
    route_label: str
    hits: tuple[Hit, ...]
    blocking: bool
    notify_parent: bool


@dataclass(frozen=True)
class Hazard:
    edge_id: str
    status: str
    distance_m: float


def route_hits(edge_ids: Iterable[str], statuses: Mapping[str, str]) -> tuple[Hit, ...]:
    return tuple(Hit(e, statuses[e]) for e in edge_ids if statuses.get(e) in BLOCKING | AT_RISK)


def _warning_for(driver: Driver, statuses: Mapping[str, str]) -> PretripWarning | None:
    for route in driver.routes:
        hits = route_hits(route.edge_ids, statuses)
        if hits:
            return PretripWarning(
                driver_id=driver.id,
                route_label=route.label,
                hits=hits,
                blocking=any(h.status in BLOCKING for h in hits),
                notify_parent=driver.is_teen and driver.parent is not None,
            )
    return None


def plan_pretrip(drivers: Iterable[Driver], statuses: Mapping[str, str], moving: frozenset[str],
                 already: frozenset[tuple[str, str]], alert_id: str) -> list[PretripWarning]:
    """Warn parked drivers whose usual route crosses flooded/at-risk roads. Never moving drivers; once per alert."""
    out = []
    for d in drivers:
        if d.id in moving or (d.id, alert_id) in already:
            continue
        w = _warning_for(d, statuses)
        if w:
            out.append(w)
    return out


def lookahead(ahead: Iterable[tuple[str, float]], statuses: Mapping[str, str], lookahead_m: float) -> Hazard | None:
    """First blocking edge on the remaining route within lookahead_m. `ahead` = [(edge_id, distance_ahead_m)]."""
    for edge_id, dist in ahead:
        if dist > lookahead_m:
            return None
        status = statuses.get(edge_id)
        if status in BLOCKING:
            return Hazard(edge_id=edge_id, status=status, distance_m=dist)
    return None
