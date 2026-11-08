"""The Hill Country replay actually runs: emits its reset, the warning beat and drone events (regression:
the runner once cancelled its own task on start and emitted nothing)."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("osmnx")
from critical.loop import CriticalLoop  # noqa: E402
from demo.hill_country import HillCountryDemo  # noqa: E402
from sim.region import load_region  # noqa: E402
from sim.region_flood import RegionFlood  # noqa: E402


class _Outreach:
    def __init__(self):
        self.sent = []

    async def send(self, msg):
        self.sent.append(msg)
        return {}


@pytest.mark.asyncio
async def test_replay_emits_reset_warning_beat_and_drone_flights():
    region = load_region()
    loop = CriticalLoop(region, RegionFlood(region))
    events: list[tuple[str, dict]] = []

    async def emit(t, p):
        events.append((t, p))

    demo = HillCountryDemo(loop, emit, _Outreach())
    demo.start(speed=900.0)  # 01:00 -> 01:14 warning in ~1 s of wall time
    try:
        for _ in range(120):
            await asyncio.sleep(0.1)
            if any(t == "demo.step" and p["step"] == 1 for t, p in events) and any(
                    t == "drones.update" and any(d["status"] == "flying" for d in p["drones"]) for t, p in events):
                break
    finally:
        demo.cancel()
    types = {t for t, _ in events}
    assert "region.reset" in types and "region.alert" in types
    assert any(t == "demo.step" and p["step"] == 1 for t, p in events)
    assert any(t == "drones.update" and any(d["status"] == "flying" for d in p["drones"]) for t, p in events)
    assert all(p.get("scenario") == "hill_country" for _, p in events)
