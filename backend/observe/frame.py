"""ObservationFrame: one immutable bundle of external evidence at a moment, from replay or live feeds."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Mapping, Protocol

from observe.alerts import Alert
from observe.gauges import Forecast

Mode = Literal["replay", "live"]
Health = Literal["ok", "stale", "unavailable", "not_used", "pending"]
_EMPTY: Mapping = MappingProxyType({})


@dataclass(frozen=True)
class SourceStatus:
    status: Health
    provenance: str            # live | cached | replay | none
    as_of: str | None = None   # provider observation/product time of the newest data used
    checked_at: str | None = None
    detail: str = ""
    error: str | None = None

    def public(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ObservationFrame:
    mode: Mode
    hydro_rev: int = 0                                    # bumps when gauge series change
    flood: Any = None                                     # RegionFlood built from new series; None = keep current
    alerts: tuple[Alert, ...] = ()
    rain_in_hr: Mapping[str, float | None] = field(default=_EMPTY)   # per critical point; None = no evidence
    closures: Mapping[str, str] = field(default=_EMPTY)              # point id -> reason (direct evidence)
    forecasts: tuple[Forecast, ...] = ()
    sources: Mapping[str, SourceStatus] = field(default=_EMPTY)


class Observations(Protocol):
    mode: Mode

    def frame_at(self, t: float) -> ObservationFrame: ...
