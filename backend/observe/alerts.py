"""NWS CAP alerts -> detection alerts.

Detection rules (differ from the statewide map's "recent updates" view on purpose):
- An alert counts while effective <= t < end of event (`ends`, else `expires`), however long ago it was sent.
- Updates supersede what they reference; Cancels remove what they reference. Tests/exercises are dropped.
- A polygon is authoritative where present (warnings are storm-based); zones (UGC) are used only without one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

from shapely.geometry import Point, box, shape
from shapely.geometry.base import BaseGeometry

log = logging.getLogger(__name__)

Level = Literal["warning", "watch", "advisory", "statement", "forecast"]
ACTIVE_TYPES = ("Alert", "Update")


@dataclass(frozen=True)
class Alert:
    id: str
    event: str
    level: Level
    headline: str
    effective: float                  # epoch s
    expires: float | None             # end of event; None = until withdrawn (replay)
    zones: frozenset[str] = frozenset()
    geometry: BaseGeometry | None = field(default=None, compare=False)
    emergency: bool = False
    simulated: bool = False
    source: str = "nws"
    sent: str | None = None
    area: str | None = None

    def active_at(self, t: float) -> bool:
        return self.effective <= t and (self.expires is None or t < self.expires)

    @property
    def is_warning(self) -> bool:
        return self.level == "warning"

    def covers(self, lon: float, lat: float, region_zones: frozenset[str]) -> bool:
        if self.geometry is not None:
            return bool(self.geometry.covers(Point(lon, lat)))
        return bool(self.zones & region_zones)

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "event": self.event, "level": self.level, "headline": self.headline,
                "emergency": self.emergency, "simulated": self.simulated, "source": self.source,
                "at": self.sent, "area": self.area,
                "effective": _iso(self.effective), "expires": _iso(self.expires) if self.expires else None}


def _iso(t: float) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()


def _level(event: str) -> Level | None:
    if "flood" not in event.lower():
        return None
    for word, level in (("Warning", "warning"), ("Emergency", "warning"), ("Watch", "watch"),
                        ("Advisory", "advisory"), ("Statement", "statement")):
        if word in event:
            return level  # type: ignore[return-value]
    return None


def _epoch(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def _emergency(props: dict) -> bool:
    params = props.get("parameters") or {}
    threat = " ".join(params.get("flashFloodDamageThreat") or []) if isinstance(params, dict) else ""
    return "CATASTROPHIC" in threat.upper() or "FLASH FLOOD EMERGENCY" in str(props.get("headline") or "").upper()


def _parse(feature: dict) -> Alert | None:
    props = feature.get("properties")
    if not isinstance(props, dict) or props.get("status") != "Actual":
        return None
    level = _level(str(props.get("event") or ""))
    effective = _epoch(props.get("effective") or props.get("onset") or props.get("sent"))
    if level is None or effective is None:
        return None
    end = _epoch(props.get("ends")) or _epoch(props.get("expires"))
    geom = None
    if isinstance(feature.get("geometry"), dict):
        try:
            geom = shape(feature["geometry"])
        except (ValueError, TypeError, KeyError, AttributeError):
            log.warning("nws alert %s: unreadable geometry, using zones", props.get("id"))
    ugc = (props.get("geocode") or {}).get("UGC") or []
    return Alert(id=str(props.get("id") or feature.get("id")), event=str(props["event"]), level=level,
                 headline=str(props.get("headline") or props["event"]), effective=effective, expires=end,
                 zones=frozenset(str(z) for z in ugc), geometry=geom, emergency=_emergency(props),
                 sent=props.get("sent"), area=props.get("areaDesc"))


def _references(feature: dict) -> Iterable[str]:
    for ref in (feature.get("properties") or {}).get("references") or []:
        if isinstance(ref, dict) and ref.get("identifier"):
            yield str(ref["identifier"])


def parse_nws_alerts(payload: Any) -> tuple[Alert, ...]:
    """api.weather.gov /alerts/active GeoJSON -> current flood alerts (malformed rows skipped)."""
    features = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(features, list):
        return ()
    rows = [f for f in features if isinstance(f, dict) and isinstance(f.get("properties"), dict)]
    superseded = {r for f in rows for r in _references(f)}
    parsed = {id(f): _parse(f) for f in rows if f["properties"].get("messageType") in ACTIVE_TYPES}
    warning_ids = {a.id for a in parsed.values() if a is not None and a.is_warning}
    out = []
    for f in rows:
        a = parsed.get(id(f))
        if a is None or a.id in superseded:
            continue
        # A follow-up statement continuing a warning is still that warning (only a Cancel or its end stops it).
        if a.level == "statement" and warning_ids & set(_references(f)):
            a = replace(a, level="warning")
        out.append(a)
    return tuple(out)


def region_alerts(alerts: Iterable[Alert], bbox: dict, region_zones: frozenset[str]) -> tuple[Alert, ...]:
    area = box(bbox["west"], bbox["south"], bbox["east"], bbox["north"])
    return tuple(a for a in alerts
                 if (a.geometry.intersects(area) if a.geometry is not None else bool(a.zones & region_zones)))
