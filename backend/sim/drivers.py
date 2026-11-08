"""Synthetic opted-in State Farm drivers: profile, home, usual routes (as edge-id lists)."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

import networkx as nx

from app.config import DATA_DIR

DRIVERS_PATH = DATA_DIR / "drivers.json"

FIRST = ["Maria", "James", "Linda", "Robert", "Patricia", "Michael", "Barbara", "David", "Elena", "Carlos",
         "Susan", "Joseph", "Margaret", "Thomas", "Dorothy", "Daniel", "Lisa", "Jose", "Nancy", "Kevin",
         "Ava", "Liam", "Sofia", "Noah", "Emma", "Mateo", "Olivia", "Ethan", "Grace", "Lucas"]
LAST = ["Garcia", "Smith", "Johnson", "Martinez", "Brown", "Lopez", "Miller", "Davis", "Hernandez", "Wilson",
        "Anderson", "Thomas", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White", "Harris"]
VEHICLES = [
    ("Toyota", "Camry", "sedan"), ("Honda", "Civic", "compact"), ("Tesla", "Model 3", "ev"),
    ("Ford", "F-150", "truck"), ("Chevrolet", "Silverado", "truck"), ("Toyota", "RAV4", "suv"),
    ("Honda", "Odyssey", "minivan"), ("Nissan", "Altima", "sedan"), ("Hyundai", "Elantra", "compact"),
    ("Jeep", "Grand Cherokee", "suv"), ("Chevrolet", "Bolt", "ev"), ("Ram", "1500", "truck"),
]


@dataclass(frozen=True)
class Vehicle:
    make: str
    model: str
    type: str


@dataclass(frozen=True)
class Contact:
    name: str
    relation: str
    phone: str  # "env:DEMO_PHONE_C" for demo drivers; fake 555 numbers otherwise


@dataclass(frozen=True)
class Route:
    label: str
    dest_node: int
    edge_ids: tuple[str, ...]
    length_m: float


@dataclass(frozen=True)
class Driver:
    id: str
    name: str
    age: int
    sex: str
    vehicle: Vehicle
    home_node: int
    phone: str
    emergency_contact: Contact
    routes: tuple[Route, ...]
    parent: Contact | None = None
    is_demo: bool = False
    demo_role: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_teen(self) -> bool:
        return self.age <= 19


def path_edge_ids(graph: nx.MultiDiGraph, nodes: list[int]) -> tuple[tuple[str, ...], float]:
    ids, total = [], 0.0
    for u, v in zip(nodes[:-1], nodes[1:]):
        key, data = min(graph[u][v].items(), key=lambda kv: kv[1].get("length", 0.0))
        ids.append(f"{u}-{v}-{key}")
        total += float(data.get("length", 0.0))
    return tuple(ids), total


def shortest_route(graph: nx.MultiDiGraph, src: int, dst: int, label: str) -> Route | None:
    try:
        nodes = nx.shortest_path(graph, src, dst, weight="length")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None
    if len(nodes) < 3:
        return None
    ids, length = path_edge_ids(graph, nodes)
    return Route(label=label, dest_node=dst, edge_ids=ids, length_m=round(length, 1))


def fake_phone(rng: random.Random) -> str:
    return f"+1830555{rng.randint(1000, 9999)}"


def _driver_from_dict(d: dict) -> Driver:
    return Driver(
        id=d["id"], name=d["name"], age=d["age"], sex=d["sex"], vehicle=Vehicle(**d["vehicle"]),
        home_node=d["home_node"], phone=d["phone"], emergency_contact=Contact(**d["emergency_contact"]),
        routes=tuple(Route(r["label"], r["dest_node"], tuple(r["edge_ids"]), r["length_m"]) for r in d["routes"]),
        parent=Contact(**d["parent"]) if d.get("parent") else None,
        is_demo=d.get("is_demo", False), demo_role=d.get("demo_role", ""), tags=tuple(d.get("tags", ())),
    )


def save_drivers(drivers: list[Driver], path: Path = DRIVERS_PATH) -> None:
    path.write_text(json.dumps([asdict(d) for d in drivers], indent=1))


def load_drivers(path: Path = DRIVERS_PATH) -> list[Driver]:
    return [_driver_from_dict(d) for d in json.loads(path.read_text())]
