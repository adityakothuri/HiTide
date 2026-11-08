"""Replay <-> live mode switching on the Hill Country runtime (no network: fetchers stubbed)."""

import asyncio

import pytest

from app import hill_runtime
from observe.http import Fetched
from observe.live import LiveObservations


@pytest.mark.asyncio
async def test_switch_to_live_steps_on_wall_clock_and_back_to_replay(monkeypatch):
    events: list[tuple[str, dict]] = []

    async def emit(typ, payload):
        events.append((typ, payload))

    async def no_network(*a, **k):
        return Fetched(None, "none", "offline_test")

    async def no_text(url):
        raise OSError("offline_test")

    h = await asyncio.to_thread(hill_runtime._build, emit)
    static = {s: (i.lon, i.lat) for s, i in h.flood.info.items()}
    h.live = LiveObservations(h.region, h.loop.points, static, h.flood.celerity, fetch_json=no_network,
                              fetch_text=no_text)
    await hill_runtime.set_mode(h, "live")
    assert h.mode == "live" and h.loop.simulate_drones is False and h.loop.observations is h.live
    for _ in range(100):
        if h.loop.snapshot.get("sim_time") is not None:  # the step has finished, not just started
            break
        await asyncio.sleep(0.05)
    assert h.loop.t is not None and h.running
    snap = h.loop.snapshot
    assert snap["mode"] == "live" and snap["sources"]["nws_alerts"]["status"] == "unavailable"
    assert snap["sources"]["mrms"]["error"] == "OSError"
    assert not snap["alerts"] and all(d["status"] == "idle" for d in snap["drones"])
    assert ("region.reset", {"scenario": "hill_country", "mode": "live"}) in events

    await hill_runtime.set_mode(h, "replay")
    assert h.mode == "replay" and h.loop.simulate_drones is True and h.loop.observations is h.replay_obs
    assert h.loop.t is None and not h.running and h.live_task is None
    await hill_runtime.shutdown(h)


def test_bad_region_mode_fails_fast(monkeypatch):
    monkeypatch.setenv("REGION_MODE", "lve")
    with pytest.raises(ValueError):
        hill_runtime.env_mode()
