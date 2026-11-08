"""Process-wide runtime: town, drivers, engine, hub. Built once in the FastAPI lifespan."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.ws import WsHub
from app.config import settings
from sim.drivers import Driver, load_drivers
from sim.engine import Engine
from sim.town import Town, load_town


@dataclass
class Runtime:
    town: Town
    drivers: list[Driver]
    hub: WsHub
    engine: Engine

    def driver_public(self, d: Driver) -> dict[str, Any]:
        node = self.town.graph.nodes[d.home_node]
        return {"id": d.id, "name": d.name, "lat": node["y"], "lon": node["x"], "heading_deg": 0.0,
                "situation": "parked", "is_demo": d.is_demo, "urgency": 0.0}

    def snapshot(self) -> dict[str, Any]:
        e = self.engine
        return {
            "t_sim_s": round(e.t_sim_s, 1),
            "river_wse_m": round(e.flood.river_wse_m, 2),
            "alert": e.alert,
            "segments": e.segment_states(),
            "drivers": [self.driver_public(d) for d in self.drivers],
            "cases": [],
            "drones": [],
            "counters": {"drivers_warned": 0, "drivers_rerouted": 0, "cars_stopped_in_water": 0,
                         "people_verified": 0, "est_claims_avoided_usd": 0},
        }


def build_runtime() -> Runtime:
    town = load_town()
    drivers = load_drivers()
    hub = WsHub()
    engine = Engine(town=town, drivers=drivers, emit=hub.emit, speed=float(settings()["clock"]["demo_speed"]))
    return Runtime(town=town, drivers=drivers, hub=hub, engine=engine)
