"""Live data feeds with cache fallback: NWS alerts, USGS gage height, USGS flood impacts."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from feeds.drivetexas import collect_work_zones
from feeds.intake import FeedRequest, RawEnvelope, split_response
from feeds.local_sensors import collect_local_sensors
from feeds.noaa_products import collect_noaa_products
from feeds.nws import active_alerts, collect_alerts
from feeds.regional_roads import collect_regional_roads
from feeds.texas import collect_texas_alerts, collect_texas_gages
from feeds.texas_roads import collect_texas_road_reports
from feeds.usgs_flood_impacts import collect_impacts, flood_impacts
from feeds.usgs_ogc import collect_gage, gage_height

__all__ = ["active_alerts", "all_feeds", "collect_raw", "flood_impacts", "gage_height"]


Scope = Literal["texas", "kerrville"]

# Failure envelopes must carry the real source id, not the collector's function name.
_COLLECTOR_SOURCE = {"collect_texas_alerts": "nws_alerts", "collect_texas_gages": "usgs_gage",
                     "collect_texas_road_reports": "nws_local_storm_reports", "collect_work_zones": "drivetexas_work_zones"}


async def _bounded_collection(collector) -> list[RawEnvelope]:
    try:
        return await asyncio.wait_for(collector(), timeout=60)
    except Exception as exc:  # noqa: BLE001 - isolate provider failures at the collection boundary
        name = _COLLECTOR_SOURCE.get(collector.__name__, collector.__name__.removeprefix("collect_"))
        request = FeedRequest(name, collector.__name__.removeprefix("collect_"), "", {}, {"state": "TX"}, "features")
        return split_response(request, {"source": "unavailable", "data": None,
                                       "errors": (f"collector_{type(exc).__name__}",)})


async def collect_raw(*, scope: Scope | None = None, cache_only: bool = False) -> list[RawEnvelope]:
    """Statewide raw intake by default. Local historical caches are a test fixture."""
    if scope is None:
        scope = "kerrville" if cache_only else "texas"
    if scope == "texas":
        if cache_only:
            raise ValueError("Offline fixtures cover Kerrville only; specify scope='kerrville'")
        collectors = (collect_texas_alerts, collect_texas_gages, collect_texas_road_reports, collect_work_zones,
                      collect_noaa_products, collect_regional_roads, collect_local_sensors)
        batches = await asyncio.gather(*(_bounded_collection(collector) for collector in collectors))
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
