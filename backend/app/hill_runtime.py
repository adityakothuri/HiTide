"""Hill Country replay runtime: region + flood + critical-point loop + demo. Built lazily (~5 s) on first use."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

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
    static: dict[str, Any]


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
    return HillCountry(region, flood, loop, HillCountryDemo(loop, emit, outreach), _static(region, flood, loop))


async def get_hill(app: FastAPI) -> HillCountry:
    if getattr(app.state, "hill", None) is None:
        async with _lock:
            if getattr(app.state, "hill", None) is None:
                app.state.hill = await asyncio.to_thread(_build, app.state.runtime.hub.emit)
    return app.state.hill


def state(h: HillCountry) -> dict[str, Any]:
    loop, t = h.loop, h.loop.t
    return {"scenario_running": h.demo.running, "sim_time": None if t is None else iso_or_none(t),
            "alerts": loop.alerts, "gauges": h.flood.gauge_status(t) if t else [],
            "segments": [{"edge_id": e, "status": s} for e, s in loop.seg_status.items() if s != "open"],
            "critical_points": loop.ranked_public(), "nodes": [loop.node_public(n) for n in loop.nodes],
            "drones": [d.public(t or 0.0) for d in loop.drones.values()], "counters": loop.counters()}


def iso_or_none(t: float | None) -> str | None:
    from critical.loop import iso
    return None if t is None else iso(t)
