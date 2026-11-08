"""Driver motion along a route. Immutable: every update returns a new DriverMotion."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Mapping

from shapely.geometry import LineString

from sim.town import Town

STOPPED_MPS = 0.5


@dataclass(frozen=True)
class DriverMotion:
    driver_id: str
    edge_ids: tuple[str, ...]
    dest_node: int
    offset_m: float = 0.0          # distance travelled along edge_ids
    speed_mps: float = 0.0
    cruise_mps: float = 14.0
    stationary_since_s: float | None = 0.0
    stall_at_edge: str | None = None   # car stalls when it reaches this edge (demo: flooded low spot)
    arrived: bool = False

    @property
    def moving(self) -> bool:
        """On an active trip (even if momentarily stopped). Pre-trip texts never go to these drivers."""
        return not self.arrived


def total_length(m: DriverMotion, lengths: Mapping[str, float]) -> float:
    return sum(lengths.get(e, 0.0) for e in m.edge_ids)


def locate(m: DriverMotion, lengths: Mapping[str, float]) -> tuple[int, float]:
    """(index of current edge, metres into that edge)."""
    remaining = m.offset_m
    for i, e in enumerate(m.edge_ids):
        length = lengths.get(e, 0.0)
        if remaining < length or i == len(m.edge_ids) - 1:
            return i, min(remaining, length)
        remaining -= length
    return 0, 0.0


def current_edge(m: DriverMotion, lengths: Mapping[str, float]) -> str:
    return m.edge_ids[locate(m, lengths)[0]]


def advance(m: DriverMotion, dt_s: float, now_s: float, lengths: Mapping[str, float]) -> DriverMotion:
    if m.arrived:
        return m
    if m.stall_at_edge and current_edge(m, lengths) == m.stall_at_edge:
        return _stop(m, now_s)
    if m.speed_mps < STOPPED_MPS:
        return m if m.stationary_since_s is not None else replace(m, stationary_since_s=now_s)
    total = total_length(m, lengths)
    offset = min(total, m.offset_m + m.speed_mps * dt_s)
    if offset >= total:
        return replace(m, offset_m=total, speed_mps=0.0, arrived=True, stationary_since_s=now_s)
    moved = replace(m, offset_m=offset, stationary_since_s=None)
    if moved.stall_at_edge and current_edge(moved, lengths) == moved.stall_at_edge:
        return _stop(moved, now_s)
    return moved


def _stop(m: DriverMotion, now_s: float) -> DriverMotion:
    since = m.stationary_since_s if m.speed_mps < STOPPED_MPS and m.stationary_since_s is not None else now_s
    return replace(m, speed_mps=0.0, stationary_since_s=since)


def ahead(m: DriverMotion, lengths: Mapping[str, float]) -> list[tuple[str, float]]:
    """Remaining edges with distance from the car to each edge's start (current edge = 0)."""
    idx, into = locate(m, lengths)
    out, dist = [(m.edge_ids[idx], 0.0)], lengths.get(m.edge_ids[idx], 0.0) - into
    for e in m.edge_ids[idx + 1:]:
        out.append((e, round(dist, 1)))
        dist += lengths.get(e, 0.0)
    return out


_GEOM_CACHE: dict[str, LineString] = {}


def _geom(edge_id: str, town: Town) -> LineString:
    if edge_id not in _GEOM_CACHE:
        _GEOM_CACHE[edge_id] = LineString(town.segments_fc["features"][town.edge_index[edge_id]]["geometry"]["coordinates"])
    return _GEOM_CACHE[edge_id]


def position(m: DriverMotion, town: Town, lengths: Mapping[str, float]) -> tuple[float, float, float]:
    """(lat, lon, heading_deg) of the car."""
    idx, into = locate(m, lengths)
    edge_id = m.edge_ids[idx]
    line = _geom(edge_id, town)
    frac = 0.0 if lengths.get(edge_id, 0.0) == 0 else into / lengths[edge_id]
    p = line.interpolate(min(1.0, frac), normalized=True)
    q = line.interpolate(min(1.0, frac + 0.05), normalized=True)
    heading = math.degrees(math.atan2(q.x - p.x, q.y - p.y)) % 360 if (q.x, q.y) != (p.x, p.y) else 0.0
    return p.y, p.x, round(heading, 1)
