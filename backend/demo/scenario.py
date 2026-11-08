"""Scripted 7-step demo (vault/Demo Script.md). Deterministic: fixed drivers, fixed flood, compressed timers."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import replace
from typing import Callable

from app.config import settings
from sim.engine import Engine
from sim.movement import DriverMotion
from stages.runner import StageRunner

log = logging.getLogger(__name__)

RAMP_SPEED = 300.0          # sim seconds per real second while the river rises
DEMO_FLOOD_MIN = 35         # must match scripts/gen_drivers.py
B_SPEED_MPS = 15.0
B_LEAD_M = 150.0            # B starts this far beyond the lookahead distance from the hazard
N_BACKGROUND_MOVERS = 15
SIM_ALERT = {
    "id": "sim-ffw-kerrville",
    "event": "Flash Flood Warning",
    "headline": "SIMULATED: Flash Flood Warning for Kerr County. Guadalupe River rising rapidly. Turn around, don't drown.",
    "active": True,
    "simulated": True,
    "polygon": None,
}
BLOCKING = ("closed", "float", "boat")


class DemoScenario:
    def __init__(self, engine: Engine, runner: StageRunner) -> None:
        self.engine = engine
        self.runner = runner
        self.task: asyncio.Task | None = None

    def start(self) -> None:
        self.cancel()
        self.task = asyncio.create_task(self._run())

    def cancel(self) -> None:
        if self.task and not self.task.done():
            self.task.cancel()

    async def _step(self, n: int, title: str, detail: str) -> None:
        log.info("demo step %d: %s", n, title)
        await self.engine.emit("demo.step", {"step": n, "title": title, "detail": detail})

    async def _wait(self, cond: Callable[[], bool], timeout_s: float, what: str) -> bool:
        for _ in range(int(timeout_s * 10)):
            if cond():
                return True
            await asyncio.sleep(0.1)
        log.warning("demo: timed out waiting for %s", what)
        return False

    async def _run(self) -> None:
        e, r = self.engine, self.runner
        world = r.world
        world.suppress_pretrip.update({"demo-b", "demo-d"})
        world.motions["demo-b"] = self._motion("demo-b", speed=0.0)

        await self._step(1, "Flash flood warning hits Kerrville",
                         "NWS-style warning (simulated). The Guadalupe rises and low roads turn red.")
        e.speed = RAMP_SPEED
        await e.begin_flood(SIM_ALERT)
        await self._wait(lambda: e.flood.t_flood_s >= DEMO_FLOOD_MIN * 60, 30, "flood ramp")
        e.speed = 1.0

        await self._wait(lambda: ("demo-a", SIM_ALERT["id"]) in world.warned, 5, "pre-trip warning A")
        await self._step(2, "Pre-trip text with a safer route",
                         "Teammate A's usual route crosses a flooded road, so they get a text before leaving. A teen driver's parent gets a copy.")
        await asyncio.sleep(3)

        self._start_background_movers()
        world.motions["demo-b"] = self._position_b()
        await self._step(3, "Driving toward a flooded crossing",
                         "Teammate B is driving. The app speaks 'Turn around' before the water and reroutes on dry roads.")
        await self._wait(lambda: "demo-b" in world.turn_arounds, 40, "turn around B")
        await asyncio.sleep(4)

        world.motions["demo-d"] = self._stall_d()
        await self._step(4, "Car stopped in floodwater at night",
                         "Margaret, 78, stalls in a flooded low spot at night. HiTide calls her. No answer.")
        await self._wait(lambda: "demo-d" in world.case_by_driver, 20, "case open")
        cid = world.case_by_driver.get("demo-d", "")
        state = lambda: world.cases[cid].state if cid in world.cases else ""  # noqa: E731

        await self._wait(lambda: state() in ("contacting_family", "drone_en_route", "verified", "handed_to_responders"), 30, "family")
        await self._step(5, "Family contacted, responders flagged",
                         "Her daughter (Teammate C) gets a text and a call. High risk, so the case goes to responders right away.")
        await self._wait(lambda: state() in ("drone_en_route", "verified", "handed_to_responders"), 30, "drone")
        await self._step(6, "Drone dispatched",
                         "A drone (simulated flight) flies to the car. Vision checks water level and people.")
        await self._wait(lambda: state() in ("verified", "handed_to_responders", "resolved"), 40, "vision")
        await self._step(7, "Verified and handed to responders",
                         "Vision: water at the windows, one person on the roof. Boat required. The counters update.")

    # ---- placement helpers -------------------------------------------
    def _route(self, driver_id: str):
        return self.runner.drivers[driver_id].routes[0]

    def _motion(self, driver_id: str, speed: float) -> DriverMotion:
        route = self._route(driver_id)
        return DriverMotion(driver_id, route.edge_ids, route.dest_node, speed_mps=speed, cruise_mps=B_SPEED_MPS,
                            stationary_since_s=None if speed else self.engine.t_sim_s)

    def _first_hazard_offset(self, driver_id: str, min_depth: float = 0.0) -> tuple[str, float]:
        lengths, offset = self.runner.lengths, 0.0
        for eid in self._route(driver_id).edge_ids:
            if self.engine.status_of(eid) in BLOCKING and self.engine.depth_of(eid) >= min_depth:
                return eid, offset
            offset += lengths.get(eid, 0.0)
        raise RuntimeError(f"no flooded edge on {driver_id}'s route; flood state does not match gen_drivers")

    def _position_b(self) -> DriverMotion:
        _, hz_offset = self._first_hazard_offset("demo-b")
        look = float(settings()["stages"]["enroute_lookahead_m"])
        start = max(0.0, hz_offset - look - B_LEAD_M)
        return replace(self._motion("demo-b", B_SPEED_MPS), offset_m=start)

    def _stall_d(self) -> DriverMotion:
        edge, offset = self._first_hazard_offset("demo-d", min_depth=12.0)
        m = self._motion("demo-d", 0.0)
        return replace(m, offset_m=offset + 1.0, stall_at_edge=edge, stationary_since_s=self.engine.t_sim_s)

    def _start_background_movers(self) -> None:
        rng = random.Random(7)
        pool = [d for d in self.runner.drivers.values() if not d.is_demo]
        for d in rng.sample(pool, N_BACKGROUND_MOVERS):
            route = d.routes[0]
            self.runner.world.motions[d.id] = DriverMotion(d.id, route.edge_ids, route.dest_node,
                                                           speed_mps=rng.uniform(11, 16), stationary_since_s=None)
