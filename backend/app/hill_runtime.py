"""Hill Country runtime: region + flood + critical-point loop, in replay (July 4, 2025) or live mode.

Built lazily (~5 s) on first use. REGION_MODE=live starts on live Texas feeds; POST /api/region/mode switches.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import FastAPI, HTTPException

from critical.loop import CriticalLoop
from demo.hill_country import HillCountryDemo
from demo.live_region import run_live
from observe.live import LiveObservations
from observe.replay import ReplayObservations
from outreach import make_outreach
from safety.hazard import Locator
from safety.monitor import SafetyMonitor
from safety.users import UserRegistry
from sim.region import Region, load_region
from sim.region_flood import RegionFlood

RegionMode = Literal["replay", "live"]
_lock = asyncio.Lock()
log = logging.getLogger(__name__)


def _log_failure(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.error("hill country live monitoring stopped", exc_info=task.exception())


@dataclass
class HillCountry:
    region: Region
    flood: RegionFlood          # replay flood (also: gauge positions and the fitted wave celerity)
    loop: CriticalLoop
    demo: HillCountryDemo
    static_json: bytes          # /api/region body, encoded once (about 3.5 MB)
    replay_obs: ReplayObservations
    emit: Any
    mode: RegionMode = "replay"
    live: LiveObservations | None = None
    live_task: asyncio.Task | None = None
    mode_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    safety: SafetyMonitor | None = None   # per-user danger pipeline (backend/safety/)

    @property
    def running(self) -> bool:
        return self.demo.running or (self.live_task is not None and not self.live_task.done())


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
            "gauges": [{"site": g.site, "name": g.name, "waterway": g.chain, "lon": g.lon, "lat": g.lat,
                        "flood_stages_ft": g.flood_stages_ft} for g in flood.info.values()],
            "stations": [{"id": s.id, "lon": s.lon, "lat": s.lat} for s in loop.stations]}


def region_dir(region: Region):
    from app.config import DATA_DIR
    return DATA_DIR / "region" / region.id


def _build(emit) -> HillCountry:
    region = load_region("hill_country")
    flood = RegionFlood(region)
    loop = CriticalLoop(region, flood)
    # Persona outreach in the scripted replay: nobody there is a moving driver.
    outreach = make_outreach(emit, lambda _driver_id: False)
    safety = _safety(region, loop, emit)
    static = json.dumps(_static(region, flood, loop)).encode()
    demo = HillCountryDemo(loop, emit, outreach, after_step=lambda: safety.after_step(loop))
    return HillCountry(region, flood, loop, demo, static, loop.observations, emit, safety=safety)


def _safety(region: Region, loop: CriticalLoop, emit) -> SafetyMonitor:
    """Users + locator + monitor. Its outreach knows who is driving (texts to a moving driver are blocked)."""
    holder: dict[str, SafetyMonitor] = {}
    outreach = make_outreach(emit, lambda uid: holder["m"].is_moving(uid) if "m" in holder else False)
    monitor = SafetyMonitor(Locator(region, loop.points), UserRegistry.load(), outreach, emit)
    holder["m"] = monitor
    return monitor


def _live(h: HillCountry) -> LiveObservations:
    if h.live is None:
        static = {s: (i.lon, i.lat) for s, i in h.flood.info.items()}
        h.live = LiveObservations(h.region, h.loop.points, static, h.flood.celerity)
    return h.live


async def _stop_live(h: HillCountry) -> None:
    task, h.live_task = h.live_task, None
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            try:
                await task
            except Exception:
                log.warning("live monitoring raised while stopping", exc_info=True)


async def set_mode(h: HillCountry, mode: RegionMode) -> None:
    """Stop whatever runs, clear the loop, and (live) start polling + stepping. Replay waits for /api/demo/start."""
    async with h.mode_lock:
        await _set_mode_locked(h, mode)


async def start_replay(h: HillCountry, speed: float) -> None:
    """Switch to replay (if needed) and start it under the same lock, so a concurrent switch can't interleave."""
    async with h.mode_lock:
        if h.mode != "replay":
            await _set_mode_locked(h, "replay")
        await h.demo.start(speed=speed)


async def _set_mode_locked(h: HillCountry, mode: RegionMode) -> None:
    await h.demo.stop()
    await _stop_live(h)
    if mode == "live":
        live = _live(h)
        await asyncio.to_thread(h.loop.configure, live, False, h.flood)
        step_s = float(h.region.cfg["live"]["step_s"])
        safety = h.safety
        after = (lambda: safety.after_step(h.loop)) if safety is not None else None
        h.live_task = asyncio.create_task(run_live(h.loop, live, h.emit, step_s, after_step=after))
        h.live_task.add_done_callback(_log_failure)
    else:
        await asyncio.to_thread(h.loop.configure, h.replay_obs, True, h.flood)
    if h.safety is not None:
        h.safety.reset(mode)
    h.mode = mode
    await h.emit("region.reset", {"scenario": "hill_country", "mode": mode})


async def shutdown(h: HillCountry) -> None:
    async with h.mode_lock:
        await h.demo.stop()
        await _stop_live(h)


def env_mode() -> RegionMode:
    mode = os.environ.get("REGION_MODE", "replay")
    if mode not in ("replay", "live"):
        raise ValueError("REGION_MODE must be 'replay' or 'live'")
    return mode  # type: ignore[return-value]


async def _build_and_start(emit) -> HillCountry:
    h = await asyncio.to_thread(_build, emit)
    if env_mode() == "live":
        try:
            await set_mode(h, "live")
        except Exception:  # keep the built region (replay) rather than rebuilding on every request
            log.exception("REGION_MODE=live failed to start; staying in replay")
    return h


def warm(app: FastAPI) -> None:
    """Start building in the background at startup so the first request doesn't wait ~5 s.
    HILL_COUNTRY_WARM=0 defers it to first use (the test suite sets this)."""
    env_mode()  # fail fast on a bad value
    if os.environ.get("HILL_COUNTRY_WARM", "1") == "0" and not hasattr(app.state, "hill_task"):
        return
    app.state.hill_task = asyncio.create_task(_build_and_start(app.state.runtime.hub.emit))
    app.state.hill_task.add_done_callback(lambda t: _expose_safety(app, t))


def _expose_safety(app: FastAPI, task: asyncio.Task) -> None:
    """Inbound replies (outreach/inbound.py) reach the safety monitor through the runtime."""
    if not task.cancelled() and task.exception() is None:
        app.state.runtime.safety = task.result().safety


async def get_hill(app: FastAPI) -> HillCountry:
    async with _lock:
        task = getattr(app.state, "hill_task", None)
        if task is None or (task.done() and (task.cancelled() or task.exception() is not None)):
            app.state.hill_task = task = asyncio.create_task(_build_and_start(app.state.runtime.hub.emit))
            task.add_done_callback(lambda t: _expose_safety(app, t))
    try:
        return await asyncio.shield(task)  # a cancelled request never orphans the build
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Hill Country scenario failed to load; see server log") from exc


def state_json(h: HillCountry) -> bytes:
    return json.dumps({**h.loop.snapshot, "scenario_running": h.running}).encode()
