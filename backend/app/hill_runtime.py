"""Hill Country replay runtime: region + flood + critical-point loop + demo. Built lazily (~5 s) on first use."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, HTTPException

from critical.loop import CriticalLoop
from demo.hill_country import HillCountryDemo
from outreach import make_outreach
from sim.region import Region, load_region
from sim.region_flood import RegionFlood

_lock = asyncio.Lock()


@dataclass
class HillCountry:
    region: Region
    flood: RegionFlood
    loop: CriticalLoop
    demo: HillCountryDemo
    static_json: bytes          # /api/region body, encoded once (about 3.5 MB)


def _static(region: Region, flood: RegionFlood, loop: CriticalLoop) -> dict[str, Any]:
    segs = [{"type": "Feature", "geometry": f["geometry"],
             "properties": {k: f["properties"][k] for k in ("edge_id", "name", "highway", "bridge")}}
            for f in region.segments_fc["features"]]
    ww = json.loads((region_dir(region) / "waterways.geojson").read_text())["features"]
    waterways = [{"type": "Feature", "geometry": f["geometry"], "properties": {"name": f["properties"]["name"],
                  "role": f["properties"]["role"]}} for f in ww]
    return {"id": region.id, "name": region.cfg["name"], "bbox": region.cfg["bbox"],
            "segments": {"type": "FeatureCollection", "features": segs},
            "waterways": {"type": "FeatureCollection", "features": waterways},
            "gauges": [{"site": g.site, "name": g.name, "waterway": g.chain, "lon": g.lon, "lat": g.lat} for g in flood.info.values()],
            "stations": [{"id": s.id, "lon": s.lon, "lat": s.lat} for s in loop.stations]}


def region_dir(region: Region):
    from app.config import DATA_DIR
    return DATA_DIR / "region" / region.id


def _build(emit) -> HillCountry:
    region = load_region("hill_country")
    flood = RegionFlood(region)
    loop = CriticalLoop(region, flood)
    outreach = make_outreach(emit, lambda _driver_id: False)  # nobody in this scenario is a moving driver
    static = json.dumps(_static(region, flood, loop)).encode()
    return HillCountry(region, flood, loop, HillCountryDemo(loop, emit, outreach), static)


def warm(app: FastAPI) -> None:
    """Start building in the background at startup so the first request doesn't wait ~5 s.
    HILL_COUNTRY_WARM=0 defers it to first use (the test suite sets this)."""
    if os.environ.get("HILL_COUNTRY_WARM", "1") == "0" and not hasattr(app.state, "hill_task"):
        return
    app.state.hill_task = asyncio.create_task(asyncio.to_thread(_build, app.state.runtime.hub.emit))


async def get_hill(app: FastAPI) -> HillCountry:
    async with _lock:
        task = getattr(app.state, "hill_task", None)
        if task is None or (task.done() and (task.cancelled() or task.exception() is not None)):
            app.state.hill_task = task = asyncio.create_task(asyncio.to_thread(_build, app.state.runtime.hub.emit))
    try:
        return await asyncio.shield(task)  # a cancelled request never orphans the build
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Hill Country scenario failed to load; see server log") from exc


def state_json(h: HillCountry) -> bytes:
    return json.dumps({**h.loop.snapshot, "scenario_running": h.demo.running}).encode()
