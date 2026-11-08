"""SafetyContext: an immutable copy of what the Hill Country loop believes at one moment.

Built under the loop lock right after a step, then read by many user assessments without holding the lock.
Everything here is BELIEF (gauges, NWS, radar, reports, drones): never the replay's truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np

from app.config import fusion_settings
from observe.alerts import Alert
from observe.frame import SourceStatus

_EMPTY: Mapping = MappingProxyType({})
# Source health that means "we can't see" for that evidence type.
DEGRADED = frozenset({"stale", "unavailable"})


@dataclass(frozen=True)
class SafetyContext:
    t: float | None
    mode: str
    belief_in: np.ndarray                         # per region edge, inches (0 where unknown: see `known`)
    known: np.ndarray                             # per region edge, bool
    point_status: Mapping[str, str] = field(default=_EMPTY)    # critical point -> open|unknown|likely|confirmed
    point_p: Mapping[str, float] = field(default=_EMPTY)
    alerts: tuple[Alert, ...] = ()                # active at t (any level)
    region_zones: frozenset[str] = frozenset()
    rain_in_hr: Mapping[str, float | None] = field(default=_EMPTY)   # per critical point
    closures: Mapping[str, str] = field(default=_EMPTY)              # critical point -> reason
    rising_waterways: frozenset[str] = frozenset()                   # online gauge rising fast
    gauge_category: Mapping[str, str | None] = field(default=_EMPTY) # waterway -> worst NWS category now
    forecast_category: Mapping[str, str | None] = field(default=_EMPTY)  # waterway -> forecast crest category
    sources: Mapping[str, SourceStatus] = field(default=_EMPTY)

    @property
    def ready(self) -> bool:
        return self.t is not None

    def degraded_sources(self) -> tuple[str, ...]:
        return tuple(sorted(k for k, s in self.sources.items() if s.status in DEGRADED))


CATEGORY_RANK = {None: -1, "none": 0, "action": 1, "minor": 2, "moderate": 3, "major": 4}


def _worst(a: str | None, b: str | None) -> str | None:
    return a if CATEGORY_RANK.get(a, -1) >= CATEGORY_RANK.get(b, -1) else b


def empty_context(n_edges: int, mode: str = "replay") -> SafetyContext:
    return SafetyContext(t=None, mode=mode, belief_in=np.zeros(n_edges), known=np.zeros(n_edges, dtype=bool))


def build_context(loop: Any) -> SafetyContext:
    """Copy the loop's current belief. Takes the loop lock briefly; call from a worker thread."""
    rate = fusion_settings()["fusion"]["rising_ft_per_hr"]
    with loop.lock:
        t = loop.t
        if t is None:
            return empty_context(len(loop.region.edge_ids), loop.frame.mode)
        frame = loop.frame
        gauges = loop.flood.gauge_status(t)
        rising = frozenset(g["waterway"] for g in gauges if g["online"] and (g["rate_ft_per_hr"] or 0) >= rate)
        cats: dict[str, str | None] = {}
        for g in gauges:
            cats[g["waterway"]] = _worst(cats.get(g["waterway"]), g["flood_category"])
        site_ww = {site: info.chain for site, info in loop.flood.info.items()}
        fcats: dict[str, str | None] = {}
        for f in frame.forecasts:
            ww = site_ww.get(getattr(f, "site", None))
            if ww:
                fcats[ww] = _worst(fcats.get(ww), getattr(f, "crest_category", None))
        return SafetyContext(
            t=t, mode=frame.mode,
            belief_in=np.array(loop.belief_now, dtype=float, copy=True),
            known=np.array(loop.belief_known, dtype=bool, copy=True),
            point_status=MappingProxyType(dict(loop.status)), point_p=MappingProxyType(dict(loop.p)),
            alerts=tuple(a for a in frame.alerts if a.active_at(t)),
            region_zones=loop.region_zones,
            rain_in_hr=MappingProxyType(dict(frame.rain_in_hr)), closures=MappingProxyType(dict(frame.closures)),
            rising_waterways=rising, gauge_category=MappingProxyType(cats), forecast_category=MappingProxyType(fcats),
            sources=MappingProxyType(dict(frame.sources)),
        )
