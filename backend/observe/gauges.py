"""USGS gage-height series -> RegionFlood hydro input; NOAA NWPS -> official flood categories and forecast crest.

Stage is only ever used as a rise above that gauge's own recent baseline, so the unresolved vertical datum
(station-relative gage height vs the DEM) never enters a depth calculation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

CATEGORY_ORDER = ("action", "minor", "moderate", "major")
MISSING = (-999, -9999)


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) and x not in MISSING else None


def usgs_series(payload: Any) -> list[tuple[str, float]]:
    """OGC continuous/latest-continuous items -> [(iso time, ft)] ascending, one value per time.
    Non-numeric values (equipment/ice codes) are dropped, never coerced."""
    features = payload.get("features") if isinstance(payload, dict) else None
    seen: dict[float, tuple[str, float]] = {}
    for f in features or []:
        props = f.get("properties") if isinstance(f, dict) else None
        if not isinstance(props, dict) or not isinstance(props.get("time"), str):
            continue
        value = _num(props.get("value"))
        try:
            t = datetime.fromisoformat(props["time"]).timestamp()
        except ValueError:
            continue
        if value is not None:
            seen[t] = (props["time"], value)
    return [seen[t] for t in sorted(seen)]


def build_hydro(series_by_site: Mapping[str, list[tuple[str, float]]],
                static: Mapping[str, tuple[float, float]]) -> dict[str, dict]:
    """Same shape RegionFlood reads from the replay file. A site with no data stays, with an empty series
    (it shows as offline rather than disappearing)."""
    return {site: {"lon": lon, "lat": lat, "series": [[t, v] for t, v in series_by_site.get(site, [])]}
            for site, (lon, lat) in static.items()}


def flood_category(stage: float | None, thresholds: Mapping[str, float]) -> str | None:
    if stage is None:
        return None
    cat = "none"
    for name in CATEGORY_ORDER:
        th = thresholds.get(name)
        if th is not None and stage >= th:
            cat = name
    return cat


@dataclass(frozen=True)
class Forecast:
    lid: str
    site: str
    name: str
    observed_ft: float | None
    observed_at: str | None
    observed_category: str | None
    crest_ft: float | None
    crest_at: str | None
    crest_category: str | None
    issued_at: str | None
    thresholds: dict[str, float]

    def public(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _thresholds(gauge: dict) -> dict[str, float]:
    cats = ((gauge.get("flood") or {}).get("categories") or {})
    out = {}
    for name in CATEGORY_ORDER:
        v = _num((cats.get(name) or {}).get("stage"))
        if v is not None:
            out[name] = v
    return out


def parse_nwps(gauge: dict, forecast: Any, site: str) -> Forecast:
    """NWPS /gauges/{lid} + /stageflow/forecast. A missing or 'not current' forecast gives crest None."""
    th = _thresholds(gauge)
    obs = ((gauge.get("status") or {}).get("observed") or {})
    obs_ft = _num(obs.get("primary")) if obs.get("primaryUnit") == "ft" else None
    not_current = ((gauge.get("status") or {}).get("forecast") or {}).get("floodCategory") == "fcst_not_current"
    rows = None if not_current else (forecast.get("data") if isinstance(forecast, dict) else None)
    best: tuple[float, str] | None = None
    for row in rows or []:
        v = _num(row.get("primary")) if isinstance(row, dict) else None
        if v is not None and isinstance(row.get("validTime"), str) and (best is None or v > best[0]):
            best = (v, row["validTime"])
    return Forecast(lid=str(gauge.get("lid")), site=site, name=str(gauge.get("name") or gauge.get("lid")),
                    observed_ft=obs_ft, observed_at=obs.get("validTime") if obs_ft is not None else None,
                    observed_category=flood_category(obs_ft, th),
                    crest_ft=best[0] if best else None, crest_at=best[1] if best else None,
                    crest_category=flood_category(best[0], th) if best else None,
                    issued_at=forecast.get("issuedTime") if isinstance(forecast, dict) else None, thresholds=th)
