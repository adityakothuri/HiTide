"""Drone tours to critical points: a team orienteering problem with time-decaying value and a battery limit.

Value of reaching point i at time t:  V_i(t) = priority_i * exp(-max(0, t - deadline_i) / tau)
(information is worth most before the people behind the crossing must decide; no deadline = decide now).

Each drone's tour must cover flight + hover at each stop + the return to its nearest station within
battery * (1 - reserve). Exact solutions are NP-hard. At this size (<= ~20 live points, a few drones),
greedy ratio insertion (best added value per added second, over every drone and insertion position)
followed by 2-opt is near-optimal. Only the first leg is flown: the loop re-plans after every snapshot,
because each observation changes p, the cuts and therefore the priorities (overview.md 8.5).

Flight profile: terrain-following at a constant AGL (FAA Part 107 caps at 400 ft / 122 m AGL), so a ridge
costs extra climb time instead of an illegal altitude above the valley floor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Sequence

from drone.dispatch import distance_m

Terrain = Callable[[float, float], float]
SAMPLE_M = 60.0
MAX_AGL_M = 122.0


@dataclass(frozen=True)
class FleetProfile:
    cruise_mps: float
    climb_mps: float
    agl_m: float
    hover_s: float
    reserve_frac: float
    tau_s: float


@dataclass(frozen=True)
class Station:
    id: str
    lon: float
    lat: float


@dataclass(frozen=True)
class Target:
    point_id: str
    lon: float
    lat: float
    priority: float
    deadline_s: float | None = None
    extra_hold_s: float = 0.0     # e.g. a waterline hold at a rising crossing


@dataclass(frozen=True)
class DroneState:
    drone_id: str
    lon: float
    lat: float
    battery_s: float              # remaining flight time
    busy: bool = False


@dataclass(frozen=True)
class Leg:
    distance_m: float
    climb_m: float
    time_s: float
    max_agl_m: float


@dataclass(frozen=True)
class Tour:
    drone_id: str
    stops: tuple[str, ...]
    arrival_s: tuple[float, ...]
    value: float
    return_station: str
    total_s: float
    path: tuple[tuple[float, float], ...]   # lon/lat: drone, stops..., station


def _flat(_lon: float, _lat: float) -> float:
    return 0.0


def leg(a: tuple[float, float], b: tuple[float, float], prof: FleetProfile, terrain: Terrain | None = None) -> Leg:
    """Horizontal time at cruise speed plus extra time for every metre climbed while terrain-following."""
    d = distance_m(a[1], a[0], b[1], b[0])
    terrain = terrain or _flat
    n = max(2, int(d / SAMPLE_M) + 1)
    zs = [terrain(a[0] + (b[0] - a[0]) * i / (n - 1), a[1] + (b[1] - a[1]) * i / (n - 1)) for i in range(n)]
    climb = sum(max(0.0, z1 - z0) for z0, z1 in zip(zs, zs[1:]))
    return Leg(round(d, 1), round(climb, 1), d / prof.cruise_mps + climb / prof.climb_mps, min(prof.agl_m, MAX_AGL_M))


class _Legs:
    """Memoized leg times between lon/lat points (the planner re-evaluates many orders)."""

    def __init__(self, prof: FleetProfile, terrain: Terrain | None):
        self._time = lru_cache(maxsize=None)(lambda a, b: leg(a, b, prof, terrain).time_s)

    def __call__(self, a: tuple[float, float], b: tuple[float, float]) -> float:
        return self._time(a, b)


def _value(target: Target, t: float, now: float, prof: FleetProfile) -> float:
    """No deadline means the water is changing now: value decays from the moment of planning."""
    deadline = now if target.deadline_s is None else target.deadline_s
    return target.priority * math.exp(-max(0.0, t - deadline) / prof.tau_s)


@dataclass(frozen=True)
class _Eval:
    feasible: bool
    value: float
    total_s: float
    arrivals: tuple[float, ...]
    station: Station


def _evaluate(start: tuple[float, float], now: float, route: Sequence[Target], drone: DroneState,
              stations: Sequence[Station], prof: FleetProfile, legs: _Legs) -> _Eval:
    t, pos, value, arrivals = 0.0, start, 0.0, []
    for tg in route:
        t += legs(pos, (tg.lon, tg.lat))
        arrivals.append(now + t)
        value += _value(tg, now + t, now, prof)
        t += prof.hover_s + tg.extra_hold_s
        pos = (tg.lon, tg.lat)
    home = min(stations, key=lambda s: legs(pos, (s.lon, s.lat)))
    t += legs(pos, (home.lon, home.lat))
    return _Eval(t <= drone.battery_s * (1 - prof.reserve_frac), value, t, tuple(arrivals), home)


def _two_opt(start, now, route, drone, stations, prof, legs) -> list[Target]:
    best, best_eval = list(route), _evaluate(start, now, route, drone, stations, prof, legs)
    improved = True
    while improved:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                cand = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                ev = _evaluate(start, now, cand, drone, stations, prof, legs)
                if ev.feasible and (ev.value > best_eval.value + 1e-9
                                    or (abs(ev.value - best_eval.value) <= 1e-9 and ev.total_s < best_eval.total_s - 1e-6)):
                    best, best_eval, improved = cand, ev, True
    return best


def plan(now_s: float, drones: Sequence[DroneState], targets: Sequence[Target], stations: Sequence[Station],
         prof: FleetProfile, terrain: Terrain | None = None) -> tuple[Tour, ...]:
    if not stations:
        raise ValueError("at least one station is required")
    legs = _Legs(prof, terrain)
    free = [d for d in drones if not d.busy]
    routes: dict[str, list[Target]] = {d.drone_id: [] for d in free}
    evals = {d.drone_id: _evaluate((d.lon, d.lat), now_s, [], d, stations, prof, legs) for d in free}
    pool = [t for t in targets if t.priority > 0]
    while pool:
        best = None  # (ratio, drone, target, position, eval)
        for d in free:
            base, route, start = evals[d.drone_id], routes[d.drone_id], (d.lon, d.lat)
            for tg in pool:
                for pos in range(len(route) + 1):
                    cand = route[:pos] + [tg] + route[pos:]
                    ev = _evaluate(start, now_s, cand, d, stations, prof, legs)
                    gain, cost = ev.value - base.value, max(1e-6, ev.total_s - base.total_s)
                    if ev.feasible and gain > 0 and (best is None or gain / cost > best[0]):
                        best = (gain / cost, d, tg, pos, ev)
        if best is None:
            break
        _, d, tg, pos, ev = best
        routes[d.drone_id].insert(pos, tg)
        evals[d.drone_id] = ev
        pool.remove(tg)
    tours = []
    for d in free:
        route = _two_opt((d.lon, d.lat), now_s, routes[d.drone_id], d, stations, prof, legs)
        ev = _evaluate((d.lon, d.lat), now_s, route, d, stations, prof, legs)
        path = ((d.lon, d.lat), *((t.lon, t.lat) for t in route), (ev.station.lon, ev.station.lat))
        tours.append(Tour(d.drone_id, tuple(t.point_id for t in route), ev.arrivals, round(ev.value, 3),
                          ev.station.id, round(ev.total_s, 1), path))
    return tuple(tours)
