"""Generate 100 seeded synthetic drivers (96 random + 4 scripted demo drivers).

Run: uv run python -m scripts.gen_drivers
Demo drivers' phone numbers are "env:DEMO_PHONE_X" references, resolved from .env at send time.
"""

from __future__ import annotations

import logging
import random

import networkx as nx
import numpy as np

from app.config import settings
from sim.drivers import (FIRST, LAST, VEHICLES, Contact, Driver, Route, Vehicle, fake_phone, save_drivers,
                         shortest_route)
from sim.flood import FloodParams, depth_in, river_wse, wse_at
from sim.town import Town, load_town

log = logging.getLogger("gen_drivers")
SEED = 42
N_TOTAL = 100
DEMO_FLOOD_MIN = 35  # demo scenario looks at the flood state ~35 sim minutes in


def flooded_at(town: Town, minutes: float) -> dict[str, float]:
    p = FloodParams(**settings()["flood"])
    d = depth_in(wse_at(town.river_dist_m, river_wse(minutes * 60, p), p), town.elev_m)
    return {eid: float(x) for eid, x in zip(town.edge_ids, d) if x >= settings()["road_status_in"]["closed"]}


def has_dry_alternative(graph: nx.MultiDiGraph, route: Route, closed: set[str]) -> bool:
    blocked = [tuple(map(int, e.split("-"))) for e in closed]
    view = nx.restricted_view(graph, [], blocked)
    src = int(route.edge_ids[0].split("-")[0])
    return nx.has_path(view, src, route.dest_node)


def random_driver(i: int, rng: random.Random, town: Town, nodes: list[int]) -> Driver | None:
    home = rng.choice(nodes)
    routes = []
    for label in rng.sample(["work", "school", "grocery", "church", "gym", "clinic"], k=rng.choice([2, 3])):
        r = shortest_route(town.graph, home, rng.choice(nodes), label)
        if r:
            routes.append(r)
    if len(routes) < 2:
        return None
    age = rng.choice([17, 18, 19] + list(range(22, 70)) + [70, 72, 75, 78, 81, 84])
    make, model, vtype = rng.choice(VEHICLES)
    first, last = rng.choice(FIRST), rng.choice(LAST)
    parent = Contact(f"{rng.choice(FIRST)} {last}", "parent", fake_phone(rng)) if age <= 19 else None
    return Driver(
        id=f"d-{i:03d}", name=f"{first} {last}", age=age, sex=rng.choice(["F", "M"]),
        vehicle=Vehicle(make, model, vtype), home_node=home, phone=fake_phone(rng),
        emergency_contact=Contact(f"{rng.choice(FIRST)} {last}", rng.choice(["spouse", "sibling", "child", "friend"]), fake_phone(rng)),
        routes=tuple(routes), parent=parent,
    )


def find_route(town: Town, rng: random.Random, nodes: list[int], flooded: dict[str, float], min_depth: float,
               lengths: tuple[float, float], max_depth: float = float("inf")) -> Route | None:
    closed = set(flooded)
    for _ in range(4000):
        r = shortest_route(town.graph, rng.choice(nodes), rng.choice(nodes), "usual")
        if not r or not lengths[0] <= r.length_m <= lengths[1]:
            continue
        hits = [e for e in r.edge_ids if flooded.get(e, 0) >= min_depth]
        if hits and flooded[hits[0]] > max_depth:
            continue
        # hazard must not be on the first ~third of the route (driver needs room to turn around)
        if not hits or r.edge_ids.index(hits[0]) < len(r.edge_ids) // 3:
            continue
        if has_dry_alternative(town.graph, r, closed):
            return r
    return None


def demo_drivers(town: Town, rng: random.Random, nodes: list[int]) -> list[Driver]:
    flooded = flooded_at(town, DEMO_FLOOD_MIN)
    log.info("flooded (closed+) segments at %s min: %d", DEMO_FLOOD_MIN, len(flooded))
    a = find_route(town, rng, nodes, flooded, 6, (1500, 5000))
    b = find_route(town, rng, nodes, flooded, 12, (1500, 5000))
    d = find_route(town, rng, nodes, flooded, 12, (1200, 5000), max_depth=30)  # doors-to-windows deep, not a river
    if not (a and b and d):
        raise RuntimeError("could not find demo routes; adjust DEMO_FLOOD_MIN")
    start = lambda r: int(r.edge_ids[0].split("-")[0])  # noqa: E731
    return [
        Driver(id="demo-a", name="Teammate A (demo)", age=34, sex="F", vehicle=Vehicle("Honda", "Civic", "compact"),
               home_node=start(a), phone="env:DEMO_PHONE_A",
               emergency_contact=Contact("Emergency contact", "spouse", "+18305550101"),
               routes=(Route("work", a.dest_node, a.edge_ids, a.length_m),), is_demo=True, demo_role="pretrip"),
        Driver(id="demo-b", name="Teammate B (demo)", age=27, sex="M", vehicle=Vehicle("Toyota", "Camry", "sedan"),
               home_node=start(b), phone="env:DEMO_PHONE_B",
               emergency_contact=Contact("Emergency contact", "sibling", "+18305550102"),
               routes=(Route("school", b.dest_node, b.edge_ids, b.length_m),), is_demo=True, demo_role="enroute"),
        Driver(id="demo-d", name="Margaret Hale", age=78, sex="F", vehicle=Vehicle("Toyota", "Camry", "sedan"),
               home_node=start(d), phone="+18305550199",
               emergency_contact=Contact("Teammate C (demo relative)", "daughter", "env:DEMO_PHONE_C"),
               routes=(Route("church", d.dest_node, d.edge_ids, d.length_m),), is_demo=True, demo_role="stopped",
               tags=("night_trip",)),
        Driver(id="demo-t", name="Jordan Ruiz", age=17, sex="M", vehicle=Vehicle("Hyundai", "Elantra", "compact"),
               home_node=start(a), phone="+18305550177",
               emergency_contact=Contact("Teammate A (demo parent)", "parent", "env:DEMO_PHONE_A"),
               parent=Contact("Teammate A (demo parent)", "parent", "env:DEMO_PHONE_A"),
               routes=(Route("school", a.dest_node, a.edge_ids, a.length_m),), is_demo=True, demo_role="pretrip_teen"),
    ]


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    rng = random.Random(SEED)
    np.random.seed(SEED)
    town = load_town()
    nodes = sorted(town.graph.nodes)
    drivers = demo_drivers(town, rng, nodes)
    i = 1
    while len(drivers) < N_TOTAL:
        drv = random_driver(i, rng, town, nodes)
        i += 1
        if drv:
            drivers.append(drv)
    save_drivers(drivers)
    teens = sum(d.is_teen for d in drivers)
    log.info("wrote %d drivers (%d demo, %d teens)", len(drivers), sum(d.is_demo for d in drivers), teens)


if __name__ == "__main__":
    main()
