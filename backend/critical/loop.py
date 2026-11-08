"""The critical-point loop (overview.md 8.5): score -> plan tours -> fly -> snapshot -> update -> re-score.

One `step(t)` advances everything to sim time t (epoch seconds) and returns WS events. Truth (the replay
flood) is only revealed through drone snapshots; everything else the system shows is belief.
Pure Python state, no I/O: the async demo runner owns the clock, the hub and outreach.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np
import yaml

from app.config import BACKEND_DIR, DATA_DIR, fusion_settings
from critical.access import NodeAccess, node_access, truck_access
from critical.score import Breakdown, NodeUse, PointInput, rank
from drone.dispatch import distance_m
from drone.planner import DroneState, FleetProfile, Station, Target, leg, plan
from fusion.segment_status import DroneObs, Signals, p_flooded, status
from population.nodes import access_graph
from sim.region import Region
from sim.region_flood import RegionFlood, epoch

WET_IN = 2.0             # water visibly on the road surface
TRUCK_MAX_IN = 24.0      # high-clearance truck limit (NWS: 2 ft of moving water carries away SUVs/pickups)
TOP_N = 12
NEARBY_M = 8000.0     # cut tests only consider flooded points this close to a node (far roads rarely change its exits)
EPS_PRIORITY = 0.05
OPEN_P = 0.15         # below this a point is 'open'; a flight there would not change any instruction
IMAGES = {"none": "/static/drone/flood_08.jpg", "wheels": "/static/drone/flood_07.jpg",
          "doors": "/static/drone/flood_02.jpg", "windows": "/static/drone/flood_01.jpg"}


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class Snapshot:
    """overview.md 9.5. Generated from the replay truth at arrival time: SIMULATED."""
    point_id: str
    drone_id: str
    time: str
    t: float
    water_on_road: bool
    road_covered_pct: int
    est_depth_in: float
    depth_method: str
    rising: bool
    people_seen: int
    confidence: str
    image_url: str
    simulated: bool = True


@dataclass
class DroneSim:
    id: str
    station: Station
    lon: float
    lat: float
    battery_s: float
    state: str = "idle"                     # idle | flying | snapshot | returning
    target: str | None = None
    leg_from: tuple[float, float] = (0.0, 0.0)
    leg_to: tuple[float, float] = (0.0, 0.0)
    leg_start: float = 0.0
    leg_time: float = 0.0
    hover_until: float = 0.0
    tour: tuple[str, ...] = ()
    path: tuple[tuple[float, float], ...] = ()
    km_flown: float = 0.0

    def public(self, t: float) -> dict[str, Any]:
        eta = max(0.0, self.leg_start + self.leg_time - t) if self.state in ("flying", "returning") else 0.0
        return {"id": self.id, "station": self.station.id, "lat": round(self.lat, 6), "lon": round(self.lon, 6),
                "status": self.state, "target": self.target, "eta_s": round(eta, 1),
                "battery_pct": round(100 * self.battery_s / FLEET_ENDURANCE[0], 1),
                "tour": list(self.tour), "path": [list(p) for p in self.path], "km_flown": round(self.km_flown, 2),
                "simulated": True}


FLEET_ENDURANCE = [2100.0]  # set from config at load (seconds); used for battery %


@dataclass
class NodeState:
    status: str = "ok"                      # ok | at_risk | partially_cut_off | cut_off
    instruction: str = "none"               # none | route_out | shelter_in_place | wait_for_check
    unavoidable: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    rescue: str | None = None               # truck_route | boat_required (cut-off nodes)
    truck_points: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


def load_fleet(profile: str = "production") -> tuple[FleetProfile, float, list[dict], dict]:
    cfg = yaml.safe_load((BACKEND_DIR / "config" / "drones.yaml").read_text())
    p = dict(cfg["profiles"][profile])
    endurance = float(p.pop("endurance_s"))
    return FleetProfile(**p), endurance, cfg["fleet"], cfg


class CriticalLoop:
    def __init__(self, region: Region, flood: RegionFlood, profile: str = "production", seed: int = 7):
        self.region, self.flood = region, flood
        data = json.loads((DATA_DIR / "region" / region.id / "nodes.json").read_text())
        self.points = {p["id"]: p for p in data["points"]}
        self.nodes = {n["id"]: n for n in data["nodes"]}
        self.safe = set(data["safe_nodes"])
        self.point_of = {e: p["id"] for p in self.points.values() for e in p["edge_ids"]}
        self.graph = access_graph(region)
        self.nearby = {nid: frozenset(pid for pid, p in self.points.items()
                                      if distance_m(n["lat"], n["lon"], p["lat"], p["lon"]) <= NEARBY_M)
                       for nid, n in self.nodes.items()}
        self.prof, endurance, fleet, cfg = load_fleet(profile)
        FLEET_ENDURANCE[0] = endurance
        self.cfg = cfg
        self.stations = [Station(f["station"], f["lon"], f["lat"]) for f in fleet]
        self.station_nodes = {self._snap(s.lon, s.lat) for s in self.stations}
        self.drones = {f["id"]: DroneSim(f["id"], st, st.lon, st.lat, endurance) for f, st in zip(fleet, self.stations)}
        self.rng = random.Random(seed)
        self.reset_state()

    def reset_state(self) -> None:
        self.t: float | None = None
        self.obs: dict[str, Snapshot] = {}
        self.p: dict[str, float] = {}
        self.status: dict[str, str] = {}
        self.node_state: dict[str, NodeState] = {nid: NodeState(unavoidable=tuple(n["unavoidable"]), optional=tuple(n["optional"]))
                                                 for nid, n in self.nodes.items()}
        self.access_cache: dict[tuple, NodeAccess] = {}
        self.truck_cache: dict[tuple, object] = {}
        self.ranked: list[Breakdown] = []
        self.alerts: list[dict] = []
        self.gauges_online: dict[str, bool] = {}
        self.last_plan = -math.inf
        self.force_replan = True
        self.seg_status: dict[str, str] = {}
        self.points_checked: set[str] = set()
        for d in self.drones.values():
            d.lon, d.lat, d.state, d.target, d.tour, d.path, d.km_flown = d.station.lon, d.station.lat, "idle", None, (), (), 0.0
            d.battery_s = FLEET_ENDURANCE[0]

    def _snap(self, lon: float, lat: float) -> str:
        g = self.region.graph
        best = min(g.nodes, key=lambda n: (g.nodes[n]["x"] - lon) ** 2 + (g.nodes[n]["y"] - lat) ** 2)
        return str(best)

    # ---- belief -------------------------------------------------------
    def _point_signals(self, t: float, belief_depth: np.ndarray, gauges: list[dict], warning: bool) -> dict[str, Signals]:
        rain = self.region.cfg.get("heavy_rain", {})
        raining = bool(rain) and epoch(rain["from"]) <= t <= epoch(rain["to"])
        rising_chains = {g["waterway"] for g in gauges if g["online"] and (g["rate_ft_per_hr"] or 0) >= 2.0}
        any_rising = bool(rising_chains)
        out = {}
        for pid, p in self.points.items():
            idx = [self.region.edge_index[e] for e in p["edge_ids"] if e in self.region.edge_index]
            o = self.obs.get(pid)
            drone = DroneObs(o.water_on_road, t - o.t) if o else None
            out[pid] = Signals(floodable=True, in_warning=warning,
                               gauge_rising=p["waterway"] in rising_chains,
                               model_above_road=bool(idx) and float(belief_depth[idx].max()) > 0.0,
                               heavy_rain=raining and p["lon"] < rain.get("west_of_lon", 999),
                               drone=drone, gauges_rising=any_rising)
        return out

    # ---- nodes --------------------------------------------------------
    def _access(self, node: dict, removed: frozenset[str]) -> NodeAccess:
        relevant = frozenset(removed) & self.nearby[node["id"]]
        key = (node["road_node"], relevant)
        if key not in self.access_cache:
            if node["road_node"] in self.safe:
                self.access_cache[key] = NodeAccess("connected", frozenset(), frozenset(), ())
            elif not relevant:
                self.access_cache[key] = NodeAccess("connected", frozenset(node["unavoidable"]), frozenset(node["optional"]), ())
            else:
                self.access_cache[key] = node_access(self.graph, node["road_node"], self.safe, self.point_of, relevant)
        return self.access_cache[key]

    def _node_update(self, nid: str, avoid: frozenset[str], confirmed: frozenset[str], impassable: frozenset[str]) -> NodeState:
        node = self.nodes[nid]
        relevant = avoid & frozenset(node["unavoidable"] + node["optional"]) if avoid else frozenset()
        # Removing a point can open routes over other points, so cut tests use every avoided point near this node.
        a = self._access(node, avoid if relevant else frozenset())
        lost = bool(relevant)
        if a.status == "cut_off":
            only_likely = bool(relevant - confirmed)
            if only_likely:
                return NodeState("cut_off", "wait_for_check", reasons=("Every exit is likely flooded; checking by drone",),
                                 unavoidable=tuple(sorted(relevant)))
            tkey = (node["road_node"], impassable & self.nearby[nid])
            if tkey not in self.truck_cache:
                self.truck_cache[tkey] = truck_access(self.graph, node["road_node"], self.station_nodes, self.point_of, tkey[1])
            t = self.truck_cache[tkey]
            rescue = "truck_route" if t else "boat_required"
            return NodeState("cut_off", "shelter_in_place", unavoidable=tuple(sorted(relevant)), rescue=rescue,
                             truck_points=tuple(sorted(t.points - set(self.obs))) if t else (),
                             reasons=("All exits confirmed or likely flooded", "Responders flagged"))
        unknown = [u for u in a.unavoidable if 0.15 <= self.p.get(u, 0.0) < 0.5]
        if unknown:
            return NodeState("at_risk", "wait_for_check", tuple(sorted(a.unavoidable)), tuple(sorted(a.optional)),
                             reasons=("The only way out crosses a road we can't confirm yet",))
        if lost:
            return NodeState("partially_cut_off", "route_out", tuple(sorted(a.unavoidable)), tuple(sorted(a.optional)),
                             reasons=("Some exits flooded; route avoids known flooding",))
        return NodeState("ok", "none", tuple(sorted(a.unavoidable)), tuple(sorted(a.optional)))

    # ---- scoring ------------------------------------------------------
    def _rank(self, t: float, belief_ahead: np.ndarray) -> list[Breakdown]:
        uses: dict[str, list[NodeUse]] = {pid: [] for pid in self.points}
        for nid, st in self.node_state.items():
            n = self.nodes[nid]
            base = dict(node_id=nid, households=n["households"], older_share=n["older_share"],
                        one_story_share=n["one_story_share"], cars_home_share=n["cars_home_share"])
            for u in st.unavoidable:
                uses.setdefault(u, []).append(NodeUse(kind="unavoidable", **base))
            for o in st.optional:
                uses.setdefault(o, []).append(NodeUse(kind="optional", **base))
            for tp in st.truck_points:
                uses.setdefault(tp, []).append(NodeUse(kind="truck_access", **base))
        inputs = []
        for pid, us in uses.items():
            if pid not in self.points:
                continue
            idx = [self.region.edge_index[e] for e in self.points[pid]["edge_ids"] if e in self.region.edge_index]
            urgent = bool(idx) and float(belief_ahead[idx].max()) > 0.0
            inputs.append(PointInput(pid, self.p.get(pid, 0.02), tuple(us), urgent))
        return rank(inputs)

    # ---- drones -------------------------------------------------------
    def _snapshot(self, d: DroneSim, t: float, truth: np.ndarray, truth_prev: np.ndarray) -> Snapshot:
        p = self.points[d.target]
        idx = [self.region.edge_index[e] for e in p["edge_ids"] if e in self.region.edge_index]
        depth = float(truth[idx].max()) if idx else 0.0
        rising = bool(idx) and depth > float(truth_prev[idx].max()) + 0.5
        wet = depth >= WET_IN
        noisy = round(depth * self.rng.uniform(0.8, 1.2), 1) if wet else 0.0
        level = "none" if not wet else "wheels" if depth < 12 else "doors" if depth < 24 else "windows"
        return Snapshot(p["id"], d.id, iso(t), t, wet, int(min(100, 35 + depth * 3)) if wet else 0, noisy,
                        "car_reference" if wet else "visual", rising, 0, "medium" if wet else "low", IMAGES[level])

    def _start_leg(self, d: DroneSim, t: float, to: tuple[float, float], state: str, target: str | None) -> None:
        lg = leg((d.lon, d.lat), to, self.prof, self.region.terrain)
        d.state, d.target, d.leg_from, d.leg_to, d.leg_start, d.leg_time = state, target, (d.lon, d.lat), to, t, max(1.0, lg.time_s)

    def _advance_drones(self, t: float, dt: float, truth: np.ndarray, truth_prev: np.ndarray) -> list[tuple[str, dict]]:
        events = []
        for d in self.drones.values():
            if d.state in ("flying", "returning", "snapshot"):
                d.battery_s = max(0.0, d.battery_s - dt)
            if d.state in ("flying", "returning"):
                frac = min(1.0, (t - d.leg_start) / d.leg_time)
                lon = d.leg_from[0] + (d.leg_to[0] - d.leg_from[0]) * frac
                lat = d.leg_from[1] + (d.leg_to[1] - d.leg_from[1]) * frac
                d.km_flown += distance_m(d.lat, d.lon, lat, lon) / 1000
                d.lon, d.lat = lon, lat
                if frac >= 1.0 and d.state == "flying":
                    hold = self.cfg["waterline_hold_s"] if any(b.point_id == d.target and b.urgency > 1 for b in self.ranked) else 0
                    d.state, d.hover_until = "snapshot", t + self.prof.hover_s + hold
                elif frac >= 1.0:
                    d.state, d.target, d.tour, d.path, d.battery_s = "idle", None, (), (), FLEET_ENDURANCE[0]  # battery swap
            elif d.state == "snapshot" and t >= d.hover_until:
                snap = self._snapshot(d, t, truth, truth_prev)
                self.obs[snap.point_id] = snap
                self.points_checked.add(snap.point_id)
                events.append(("snapshot.created", asdict(snap)))
                d.state, d.target = "idle", None
                d.tour = d.tour[1:]
                self.force_replan = True
        return events

    def _replan(self, t: float) -> None:
        busy = {d.target for d in self.drones.values() if d.state in ("flying", "snapshot") and d.target}
        rising = any(self.gauges_online.values())
        fresh_window = fusion_settings()["fusion"]["decay_half_life_s"]["rising" if rising else "steady"]  # overview 8.6
        targets = [Target(b.point_id, self.points[b.point_id]["lon"], self.points[b.point_id]["lat"], b.priority,
                          t + 900 if b.urgency > 1 else None,
                          self.cfg["waterline_hold_s"] if b.urgency > 1 else 0.0)
                   for b in self.ranked[:20]
                   if b.priority > EPS_PRIORITY and b.point_id not in busy
                   and not (b.point_id in self.obs and t - self.obs[b.point_id].t < fresh_window)]
        if not self.alerts:  # drones fly only when there is a warning and real uncertainty (overview 1, 9.1)
            targets = []
        truck = {tp for st in self.node_state.values() for tp in st.truck_points}
        targets = [tg for tg in targets if self.p.get(tg.point_id, 0.0) >= OPEN_P or tg.point_id in truck]
        free = [d for d in self.drones.values() if d.state == "idle"]
        states = [DroneState(d.id, d.lon, d.lat, d.battery_s) for d in free]
        tours = {tr.drone_id: tr for tr in plan(t, states, targets, self.stations, self.prof, self.region.terrain)} if states else {}
        for d in free:
            tr = tours.get(d.id)
            if tr and tr.stops:
                d.tour, d.path = tr.stops, tr.path
                p = self.points[tr.stops[0]]
                self._start_leg(d, t, (p["lon"], p["lat"]), "flying", p["id"])
            elif (d.lon, d.lat) != (d.station.lon, d.station.lat):
                home = min(self.stations, key=lambda s: distance_m(d.lat, d.lon, s.lat, s.lon))
                d.station, d.tour, d.path = home, (), ((d.lon, d.lat), (home.lon, home.lat))
                self._start_leg(d, t, (home.lon, home.lat), "returning", None)
        self.last_plan, self.force_replan = t, False

    # ---- one step -----------------------------------------------------
    def step(self, t: float) -> list[tuple[str, dict]]:
        events: list[tuple[str, dict]] = []
        dt = 0.0 if self.t is None else max(0.0, t - self.t)
        self.t = t
        for w in self.region.cfg["replay"]["warnings"]:
            if epoch(w["at"]) <= t and w not in self.alerts:
                self.alerts.append(w)
                self.force_replan = True
                events.append(("region.alert", {"id": f"replay-{len(self.alerts)}", "event": w["event"], "headline":
                               f"REPLAY of July 4, 2025: {w['event']} for {w['area']}", "active": True,
                               "simulated": True, "at": w["at"]}))
        gauges = self.flood.gauge_status(t)
        for g in gauges:
            if self.gauges_online.get(g["site"]) not in (None, g["online"]):
                self.force_replan = True
                events.append(("gauge.status", {**g, "change": "online" if g["online"] else "offline", "at": iso(t)}))
            self.gauges_online[g["site"]] = g["online"]
        truth, truth_prev = self.flood.truth_depth_in(t), self.flood.truth_depth_in(t - max(dt, 60.0))
        events += self._advance_drones(t, dt, truth, truth_prev)
        belief = self.flood.belief_depth_in(t)
        signals = self._point_signals(t, belief, gauges, warning=bool(self.alerts))
        self.p = {pid: round(p_flooded(s), 3) for pid, s in signals.items()}
        self.status = {pid: status(p) for pid, p in self.p.items()}
        avoid = frozenset(pid for pid, s in self.status.items() if s in ("likely_flooded", "confirmed_flooded"))
        confirmed = frozenset(pid for pid, s in self.status.items() if s == "confirmed_flooded")
        impassable = frozenset(pid for pid, o in self.obs.items() if o.est_depth_in >= TRUCK_MAX_IN)
        for nid in self.nodes:
            new = self._node_update(nid, avoid, confirmed, impassable)
            if new != self.node_state[nid]:
                self.node_state[nid] = new
                events.append(("node.updated", self.node_public(nid)))
        before = [b.point_id for b in self.ranked[:TOP_N]]
        self.ranked = self._rank(t, self.flood.belief_depth_in(t + self.cfg["replan_every_s"] * 12))
        if self.force_replan or t - self.last_plan >= self.cfg["replan_every_s"]:
            self._replan(t)
        if [b.point_id for b in self.ranked[:TOP_N]] != before or events:
            events.append(("critical_points.ranked", {"t": iso(t), "points": self.ranked_public()}))
        events.append(("drones.update", {"t": iso(t), "drones": [d.public(t) for d in self.drones.values()]}))
        seg = self._segment_changes(belief)
        if seg:
            events.append(("region.segments", {"segments": seg}))
        return events

    def _segment_changes(self, belief: np.ndarray) -> list[dict]:
        out = []
        point_status = {e: self.status.get(p["id"], "open") for p in self.points.values() for e in p["edge_ids"]}
        for i, eid in enumerate(self.region.edge_ids):
            s = point_status.get(eid) or ("likely_flooded" if belief[i] >= 6 else "open")
            if self.seg_status.get(eid, "open") != s:
                self.seg_status[eid] = s
                out.append({"edge_id": eid, "status": s, "belief_depth_in": round(float(belief[i]), 1)})
        return out

    # ---- public views -------------------------------------------------
    def point_public(self, b: Breakdown) -> dict[str, Any]:
        p = self.points[b.point_id]
        o = self.obs.get(b.point_id)
        return {"id": p["id"], "name": p["name"], "kind": p["kind"], "waterway": p["waterway"], "lon": p["lon"], "lat": p["lat"],
                "p_flooded": b.p, "status": self.status.get(p["id"], "open"), "priority": round(b.priority, 3),
                "breakdown": {"dependency": round(b.dependency, 1), "vulnerability": round(b.vulnerability, 3),
                              "p_weight": round(b.p_weight, 3), "uncertainty": round(b.uncertainty, 3), "urgency": b.urgency},
                "node_ids": list(b.node_ids), "last_snapshot": asdict(o) if o else None}

    def ranked_public(self) -> list[dict[str, Any]]:
        return [self.point_public(b) for b in self.ranked[:TOP_N]]

    def node_public(self, nid: str) -> dict[str, Any]:
        n, st = self.nodes[nid], self.node_state[nid]
        return {"id": nid, "name": n["name"], "kind": n["kind"], "town": n["town"], "lon": n["lon"], "lat": n["lat"],
                "households": n["households"], "status": st.status, "instruction": st.instruction,
                "unavoidable_points": list(st.unavoidable), "optional_points": list(st.optional),
                "rescue": st.rescue, "reasons": list(st.reasons)}

    def counters(self) -> dict[str, Any]:
        sts = list(self.node_state.items())
        hh = lambda pred: sum(self.nodes[n]["households"] for n, s in sts if pred(s))  # noqa: E731
        return {"households_warned": hh(lambda s: s.instruction != "none"),
                "households_route_out": hh(lambda s: s.instruction == "route_out"),
                "nodes_cut_off": sum(1 for _, s in sts if s.status == "cut_off"),
                "households_cut_off": hh(lambda s: s.status == "cut_off"),
                "points_checked": len(self.points_checked),
                "drone_km": round(sum(d.km_flown for d in self.drones.values()), 1),
                "boat_required": sum(1 for _, s in sts if s.rescue == "boat_required")}
