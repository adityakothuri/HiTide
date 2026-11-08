"""Live data feeds with cache fallback: NWS alerts, USGS gage height, USGS flood impacts."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from feeds.intake import RawEnvelope
from feeds.nws import active_alerts, collect_alerts
from feeds.usgs_flood_impacts import collect_impacts, flood_impacts
from feeds.usgs_ogc import collect_gage, gage_height
from feeds.texas import collect_texas_alerts, collect_texas_gages
from feeds.texas_roads import collect_texas_road_reports

__all__ = ["active_alerts", "all_feeds", "collect_raw", "flood_impacts", "gage_height"]


Scope = Literal["texas", "kerrville"]


async def collect_raw(*, scope: Scope | None = None, cache_only: bool = False) -> list[RawEnvelope]:
    """Statewide raw intake by default. Local historical caches are a test fixture."""
    if scope is None:
        scope = "kerrville" if cache_only else "texas"
    if scope == "texas":
        if cache_only:
            raise ValueError("Offline fixtures cover Kerrville only; specify scope='kerrville'")
        batches = await asyncio.gather(
            collect_texas_alerts(), collect_texas_gages(), collect_texas_road_reports()
        )
    elif scope == "kerrville":
        batches = await asyncio.gather(
            collect_alerts(cache_only=cache_only), collect_gage(cache_only=cache_only),
            collect_impacts(cache_only=cache_only),
        )
    else:
        raise ValueError("Unknown collection scope")
    return [record for batch in batches for record in batch]


async def all_feeds() -> dict[str, Any]:
    """Fetch all feeds concurrently. Each feed handles its own failures."""
    alerts, gage, impacts = await asyncio.gather(active_alerts(), gage_height(), flood_impacts())
    return {"nws_alerts": alerts, "usgs_gage": gage, "usgs_flood_impacts": impacts}
