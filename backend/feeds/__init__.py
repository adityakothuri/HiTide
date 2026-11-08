"""Live data feeds with cache fallback: NWS alerts, USGS gage height, USGS flood impacts."""

from __future__ import annotations

import asyncio
from typing import Any

from feeds.nws import active_alerts
from feeds.usgs_flood_impacts import flood_impacts
from feeds.usgs_ogc import gage_height

__all__ = ["active_alerts", "all_feeds", "flood_impacts", "gage_height"]


async def all_feeds() -> dict[str, Any]:
    """Fetch all feeds concurrently. Each feed handles its own failures."""
    alerts, gage, impacts = await asyncio.gather(active_alerts(), gage_height(), flood_impacts())
    return {"nws_alerts": alerts, "usgs_gage": gage, "usgs_flood_impacts": impacts}
