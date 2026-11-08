"""Process-wide runtime: town, drivers, engine, stage runner, hub. Built once in the FastAPI lifespan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.ws import WsHub
from demo.scenario import DemoScenario
from drone import dispatch
from sim.drivers import Driver, load_drivers
from sim.engine import Engine
from sim.town import Town, load_town
from stages.runner import StageRunner


@dataclass
class Runtime:
    town: Town
    drivers: list[Driver]
    hub: WsHub
    engine: Engine
    runner: StageRunner
    demo: DemoScenario

    def snapshot(self) -> dict[str, Any]:
        e, r = self.engine, self.runner
        return {
            "t_sim_s": round(e.t_sim_s, 1),
            "river_wse_m": round(e.flood.river_wse_m, 2),
            "alert": e.alert,
            "segments": e.segment_states(),
            # privacy: locations only while a flash flood warning is active (opt-in terms)
            "drivers": [r.driver_public(d) for d in self.drivers] if e.alert else [],
            "drivers_opted_in": len(self.drivers),
            "cases": [c.model_dump(mode="json") for c in self.sorted_cases()],
            "drones": [dispatch.state(d, e.t_sim_s) for d in r.world.drones.values()],
            "counters": r.counters(),
        }

    def sorted_cases(self):
        return sorted(self.runner.world.cases.values(), key=lambda c: c.urgency, reverse=True)

    async def reset(self) -> None:
        self.demo.cancel()
        self.engine.reset()
        self.engine.speed = 1.0
        self.runner.reset()
        await self.hub.emit("snapshot", self.snapshot())


def build_runtime() -> Runtime:
    town = load_town()
    drivers = load_drivers()
    hub = WsHub()
    engine = Engine(town=town, drivers=drivers, emit=hub.emit, speed=1.0)
    runner = StageRunner(engine, drivers)
    return Runtime(town=town, drivers=drivers, hub=hub, engine=engine, runner=runner, demo=DemoScenario(engine, runner))
