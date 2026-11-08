"""NWS Local Storm Reports (via Iowa Environmental Mesonet) -> closures at critical points.

A trained-spotter / public / official report of flooding that names a road, located within REPORT_RADIUS_M of a
crossing, is direct evidence for that crossing. Anything else stays context: report positions are often
"2 N of town", so the radius is deliberately small.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Mapping

from drone.dispatch import distance_m
from feeds.texas_roads import ROAD_MENTION

FLOOD_TYPES = ("FLOOD", "FLASH FLOOD")
# A report that says the water is gone is not evidence of water on the road.
NEGATED = re.compile(r"\b(?:reced(?:ed|ing)|re-?opened|no longer|water (?:has )?gone down|no water)\b", re.IGNORECASE)
REPORT_RADIUS_M = 500.0
REPORT_MAX_AGE_S = 3 * 3600.0
FUTURE_SLACK_S = 300.0


def _valid_t(props: dict) -> float | None:
    v = props.get("valid")
    if not isinstance(v, str):
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def lsr_closures(payload: Any, points: Mapping[str, Mapping[str, Any]], now: float,
                 max_age_s: float = REPORT_MAX_AGE_S, radius_m: float = REPORT_RADIUS_M) -> dict[str, str]:
    features = payload.get("features") if isinstance(payload, dict) else None
    out: dict[str, str] = {}
    for f in features or []:
        props = f.get("properties") if isinstance(f, dict) else None
        geom = f.get("geometry") if isinstance(f, dict) else None
        coords = geom.get("coordinates") if isinstance(geom, dict) else None
        if not isinstance(props, dict) or not isinstance(coords, list) or len(coords) < 2 or props.get("state") != "TX":
            continue
        remark, t = props.get("remark"), _valid_t(props)
        if (props.get("typetext") not in FLOOD_TYPES or not isinstance(remark, str) or not ROAD_MENTION.search(remark)
                or NEGATED.search(remark)
                or t is None or not (now - max_age_s <= t <= now + FUTURE_SLACK_S)):
            continue
        try:
            lon, lat = float(coords[0]), float(coords[1])
        except (TypeError, ValueError):
            continue   # one malformed report must not stall detection
        for pid, p in points.items():
            if distance_m(lat, lon, p["lat"], p["lon"]) <= radius_m:
                out[pid] = f"NWS storm report {props.get('valid')}: {remark.strip()[:160]}"
    return out
