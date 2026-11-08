"""REGION_MODE=live driver: step the Hill Country loop on wall-clock time over live Texas observations."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from critical.loop import CriticalLoop, iso
from observe.live import LiveObservations

log = logging.getLogger(__name__)
Emit = Callable[[str, dict[str, Any]], Awaitable[None]]


async def run_live(loop: CriticalLoop, live: LiveObservations, emit: Emit, step_s: float,
                   after_step: Callable[[], Awaitable[None]] | None = None) -> None:
    try:
        await live.start()   # first poll of every source (each failure is isolated), then background cadences
        while True:
            t = time.time()
            try:
                events = await asyncio.to_thread(loop.step, t)
                for typ, payload in events:
                    await emit(typ, {"scenario": "hill_country", **payload})
                await emit("region.counters", {"scenario": "hill_country", "sim_time": iso(t),
                                               **loop.snapshot.get("counters", {})})
                if after_step is not None:   # per-user danger pipeline (safety/monitor.py)
                    await after_step()
            except asyncio.CancelledError:
                raise
            except Exception:  # one bad step must not stop live monitoring
                log.exception("live region step failed at %s; continuing", iso(t))
            await asyncio.sleep(step_s)
    finally:
        await live.stop()
