"""Simulated drone: straight-line flight from the station to the stopped car. SIMULATED (labelled in UI)."""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_M_PER_DEG = 111_320.0


@dataclass(frozen=True)
class Drone:
    id: str
    case_id: str
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float
    launched_s: float
    flight_s: float


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dx = (lon2 - lon1) * EARTH_M_PER_DEG * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat2 - lat1) * EARTH_M_PER_DEG
    return math.hypot(dx, dy)


def launch(case_id: str, station: dict, to_lat: float, to_lon: float, now_s: float, speed_mps: float,
           max_flight_s: float | None = None) -> Drone:
    flight = distance_m(station["lat"], station["lon"], to_lat, to_lon) / speed_mps
    if max_flight_s:
        flight = min(flight, max_flight_s)
    return Drone(f"drone-{case_id}", case_id, station["lat"], station["lon"], to_lat, to_lon, now_s, max(flight, 1.0))


def arrived(d: Drone, now_s: float) -> bool:
    return now_s - d.launched_s >= d.flight_s


def state(d: Drone, now_s: float) -> dict:
    frac = min(1.0, max(0.0, (now_s - d.launched_s) / d.flight_s))
    status = "on_scene" if frac >= 1.0 else ("launching" if frac < 0.05 else "en_route")
    return {
        "id": d.id, "case_id": d.case_id,
        "lat": d.from_lat + (d.to_lat - d.from_lat) * frac,
        "lon": d.from_lon + (d.to_lon - d.from_lon) * frac,
        "eta_s": round(max(0.0, d.flight_s - (now_s - d.launched_s)), 1),
        "status": status,
    }
