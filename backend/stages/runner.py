"""Stage runner: plugs Stages 1-3, drones and counters into the engine tick.

World holds the live state. Values inside it (DriverMotion, Case, Drone) are immutable and get replaced, never mutated.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from api.schemas import Case, TimelineEntry, VisionResult
from app.config import settings
from drone import dispatch
from outreach import OutboundMessage, make_outreach, voice_elevenlabs
from outreach.call_summary import call_variables, classify_call, first_name, follow_up_text, opening_line
from scoring.risk import RiskInput, score
from sim.drivers import Driver
from sim.engine import Engine, now_iso
from sim.movement import STOPPED_MPS, DriverMotion, advance, ahead, current_edge, locate, position
from sim.routing import dry_route, edge_end, edge_lengths, route_geojson
from stages import escalation as esc
from stages.route_check import lookahead, plan_pretrip
from stages.stop_detect import is_stopped_in_water
from vision.catalog import result_for

log = logging.getLogger(__name__)
TURN_AROUND_MSG = "Flooded road ahead. Turn around."
NIGHT_HOUR, DAY_HOUR = 23, 14
WATER_LEVEL_IN = {"none": 0.0, "wheels": 12.0, "doors": 20.0, "windows": 30.0, "roof": 50.0}  # sedan, approx.
CALL_POLL_INTERVAL_S = 3.0  # how often the post-call watcher asks ElevenLabs for the conversation
CALL_WATCH_MAX_S = 180.0
CALL_DONE_STATUSES = frozenset({"done", "failed"})
SEND_BUDGET_S = 8.0  # a slow Photon/ElevenLabs call must never freeze the tick for long


@dataclass
class World:
    motions: dict[str, DriverMotion] = field(default_factory=dict)
    warned: set[tuple[str, str]] = field(default_factory=set)
    pretrip_cards: dict[str, dict[str, Any]] = field(default_factory=dict)
    suppress_pretrip: set[str] = field(default_factory=set)
    handled_hazards: set[tuple[str, str]] = field(default_factory=set)
    rerouted: set[str] = field(default_factory=set)
    turn_arounds: dict[str, dict[str, Any]] = field(default_factory=dict)
    cases: dict[str, Case] = field(default_factory=dict)
    case_by_driver: dict[str, str] = field(default_factory=dict)
    case_opened_s: dict[str, float] = field(default_factory=dict)
    case_fired: dict[str, frozenset[str]] = field(default_factory=dict)
    drones: dict[str, dispatch.Drone] = field(default_factory=dict)
    last_counters: dict[str, int] = field(default_factory=dict)


class StageRunner:
    def __init__(self, engine: Engine, drivers: list[Driver]) -> None:
        self.engine = engine
        self.drivers = {d.id: d for d in drivers}
        self.lengths = edge_lengths(engine.town)
        self.world = World()
        self.profile = os.environ.get("SIM_PROFILE", "demo")
        self.outreach = make_outreach(engine.emit, self.is_physically_moving)
        self._pending: set[asyncio.Task] = set()
        engine.hooks.extend([self.movement_hook, self.pretrip_hook, self.enroute_hook, self.stopped_hook,
                             self.drone_hook, self.counters_hook])

    # ---- helpers -------------------------------------------------------
    def reset(self) -> None:
        self.world = World()

    def is_physically_moving(self, driver_id: str) -> bool:
        m = self.world.motions.get(driver_id)
        return bool(m and not m.arrived and m.speed_mps >= STOPPED_MPS)

    def on_trip(self) -> frozenset[str]:
        return frozenset(d for d, m in self.world.motions.items() if m.moving)

    def driver_public(self, d: Driver) -> dict[str, Any]:
        m = self.world.motions.get(d.id)
        case_id = self.world.case_by_driver.get(d.id)
        urgency = self.world.cases[case_id].urgency if case_id else 0.0
        if m:
            lat, lon, heading = position(m, self.engine.town, self.lengths)
            situation = "stopped_in_water" if case_id else ("driving" if m.moving else "parked")
        else:
            node = self.engine.town.graph.nodes[d.home_node]
            lat, lon, heading = node["y"], node["x"], 0.0
            situation = "planning" if d.id in self.world.pretrip_cards else "parked"
        return {"id": d.id, "name": d.name, "lat": lat, "lon": lon, "heading_deg": heading,
                "situation": situation, "is_demo": d.is_demo, "urgency": urgency}

    def _hour(self, d: Driver) -> int:
        return NIGHT_HOUR if "night_trip" in d.tags else DAY_HOUR

    def _rise_in_per_min(self) -> float:
        p = self.engine.params
        return 0.0 if not self.engine.flood.active or self.engine.flood.river_wse_m >= p.base_wse_m + p.max_rise_m \
            else p.rise_m_per_min * 39.37

    @staticmethod
    def _message(d: Driver, recipient: str, channel: str, body: str, phone: str, case_id: str | None,
                 poll: tuple[str, ...], variables: dict[str, str] | None) -> OutboundMessage:
        if not variables:
            return OutboundMessage(d.id, recipient, channel, body, phone, case_id, poll)
        try:
            return OutboundMessage(d.id, recipient, channel, body, phone, case_id, poll, variables=variables)
        except TypeError:  # OutboundMessage without a variables field: call still goes out, just without context
            log.warning("OutboundMessage has no variables field; voice call placed without dynamic variables")
            return OutboundMessage(d.id, recipient, channel, body, phone, case_id, poll)

    async def _send(self, d: Driver, recipient: str, channel: str, body: str, case_id: str | None = None,
                    poll: tuple[str, ...] = (), variables: dict[str, str] | None = None) -> dict:
        phone = {"driver": d.phone, "parent": d.parent.phone if d.parent else "",
                 "emergency_contact": d.emergency_contact.phone}[recipient]
        msg = self._message(d, recipient, channel, body, phone, case_id, poll, variables)
        task = asyncio.ensure_future(self.outreach.send(msg))
        try:
            return await asyncio.wait_for(asyncio.shield(task), SEND_BUDGET_S)
        except asyncio.TimeoutError:
            # keep the tick moving; the send finishes in the background and still logs + emits its own event
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)
            log.warning("outreach send to %s/%s still pending after %.0fs", d.id, recipient, SEND_BUDGET_S)
            return {"mode": "photon", "status": "queued"}

    # ---- movement ------------------------------------------------------
    async def movement_hook(self, e: Engine) -> None:
        if not self.world.motions:
            return
        dt = e.last_dt
        self.world.motions = {k: advance(m, dt, e.t_sim_s, self.lengths) for k, m in self.world.motions.items()}
        visible = [self.driver_public(self.drivers[k]) for k, m in self.world.motions.items()
                   if m.moving or self.drivers[k].is_demo]
        if visible and e.alert:  # privacy: live location is shared only during an active warning
            await e.emit("drivers.update", {"drivers": visible})

    # ---- Stage 1: pre-trip --------------------------------------------
    async def pretrip_hook(self, e: Engine) -> None:
        if not e.alert:
            return
        candidates = [d for d in self.drivers.values() if d.id not in self.world.suppress_pretrip]
        warnings = plan_pretrip(candidates, e.statuses, moving=self.on_trip(),
                                already=frozenset(self.world.warned), alert_id=e.alert["id"])
        for w in warnings:
            await self._warn(e, self.drivers[w.driver_id], w)

    async def _warn(self, e: Engine, d: Driver, w) -> None:
        self.world.warned.add((d.id, e.alert["id"]))
        route = next(r for r in d.routes if r.label == w.route_label)
        names = sorted({e.town.segment_name(h.edge_id) for h in w.hits})[:2]
        alt = dry_route(e.town.graph, d.home_node, route.dest_node, e.closed_edges(), "safer") if w.blocking else None
        where = " and ".join(names)
        body = (f"State Farm Flood Watch: Flash flood warning. Your usual route to {route.label} crosses flooded "
                f"roads at {where}. " + ("Use the safer route we sent to your app." if alt else
                                         "No dry route right now. Please delay your trip.") + " Turn around, don't drown.")
        self.world.pretrip_cards[d.id] = {"route_label": route.label, "flooded_roads": names, "blocking": w.blocking,
                                          "alt_route": route_geojson(e.town, alt.edge_ids) if alt else None,
                                          "alt_distance_m": alt.length_m if alt else None, "message": body}
        await self._send(d, "driver", "text", body)
        if w.notify_parent:
            await self._send(d, "parent", "text", f"Copy for parent of {d.name.split()[0]}: {body}")
        if alt:
            await e.emit("reroute", {"driver_id": d.id, "reason": "pre-trip: safer route", "blocked_edge_ids":
                                     [h.edge_id for h in w.hits], "route": route_geojson(e.town, alt.edge_ids),
                                     "distance_m": alt.length_m})

    # ---- Stage 2: en route --------------------------------------------
    async def enroute_hook(self, e: Engine) -> None:
        look = float(settings()["stages"]["enroute_lookahead_m"])
        for did, m in list(self.world.motions.items()):
            if not self.is_physically_moving(did):
                continue
            hz = lookahead(ahead(m, self.lengths), e.statuses, look)
            if hz and (did, hz.edge_id) not in self.world.handled_hazards:
                await self._turn_around(e, self.drivers[did], m, hz)

    async def _turn_around(self, e: Engine, d: Driver, m: DriverMotion, hz) -> None:
        world = self.world
        world.handled_hazards.add((d.id, hz.edge_id))
        ta = {"driver_id": d.id, "message": TURN_AROUND_MSG, "hazard_edge_id": hz.edge_id,
              "hazard_depth_in": round(e.depth_of(hz.edge_id), 1), "distance_m": round(hz.distance_m, 1)}
        self.world.turn_arounds[d.id] = ta
        await e.emit("turn_around", ta)
        await self._send(d, "driver", "tts_in_app", TURN_AROUND_MSG)
        if self.world is not world:  # reset happened while we awaited
            return
        here = current_edge(m, self.lengths)
        alt = dry_route(e.town.graph, edge_end(here), m.dest_node, e.closed_edges(), "reroute")
        if not alt:
            world.motions[d.id] = replace(m, speed_mps=0.0, arrived=True)  # pulled over on dry ground
            return
        world.rerouted.add(d.id)
        _, into = locate(m, self.lengths)  # keep the car where it is: finish this edge, then take the dry route
        world.motions[d.id] = replace(m, edge_ids=(here, *alt.edge_ids), offset_m=into, stall_at_edge=None)
        await e.emit("reroute", {"driver_id": d.id, "reason": f"Flooded road ahead ({ta['hazard_depth_in']} in)",
                                 "route": route_geojson(e.town, alt.edge_ids), "blocked_edge_ids": [hz.edge_id],
                                 "distance_m": alt.length_m})

    # ---- Stage 3: stopped in water --------------------------------------
    async def stopped_hook(self, e: Engine) -> None:
        cfg = settings()["stages"]
        stop_s = float(cfg["stop_seconds"][self.profile])
        for did, m in list(self.world.motions.items()):
            if m.arrived or did in self.world.case_by_driver or m.stationary_since_s is None:
                continue
            edge = current_edge(m, self.lengths)
            dest = e.town.graph.nodes[m.dest_node]
            lat, lon, _ = position(m, e.town, self.lengths)
            if is_stopped_in_water(m.speed_mps, e.t_sim_s - m.stationary_since_s,
                                   dispatch.distance_m(lat, lon, dest["y"], dest["x"]), e.depth_of(edge),
                                   stop_s, float(cfg["dest_radius_m"])):
                await self._open_case(e, self.drivers[did], lat, lon, e.depth_of(edge))
        for cid in list(self.world.cases):
            await self._advance_case(e, cid)

    async def _open_case(self, e: Engine, d: Driver, lat: float, lon: float, depth: float) -> None:
        risk = score(RiskInput(depth_in=depth, rise_in_per_min=self._rise_in_per_min(), hour=self._hour(d),
                               age=d.age, vehicle_type=d.vehicle.type, situation="stopped_in_water"))
        cid = f"case-{len(self.world.cases) + 1:03d}"
        case = esc.open_case(cid, d.id, d.name, lat, lon, round(depth, 1), risk, now_iso())
        self.world.cases[cid] = case
        self.world.case_by_driver[d.id] = cid
        self.world.case_opened_s[cid] = e.t_sim_s
        self.world.case_fired[cid] = frozenset()
        await e.emit("case.update", case.model_dump(mode="json"))

    async def _advance_case(self, e: Engine, cid: str) -> None:
        case = self.world.cases[cid]
        elapsed = e.t_sim_s - self.world.case_opened_s[cid]
        profile = settings()["escalation_s"][self.profile]
        for kind in esc.due_timers(case, elapsed, self.world.case_fired[cid], profile):
            self.world.case_fired[cid] = self.world.case_fired[cid] | {kind}
            new = esc.transition(case, esc.Timer(kind, round(elapsed, 1)), now_iso())
            if new.state != case.state:
                new = await self._timer_action(e, new, kind, elapsed)
            case = new
        if cid in self.world.cases and case is not self.world.cases[cid]:
            self.world.cases[cid] = case
            await e.emit("case.update", case.model_dump(mode="json"))

    async def _timer_action(self, e: Engine, case: Case, kind: str, elapsed: float) -> Case:
        d = self.drivers[case.driver_id]
        if kind == "call_driver":
            street = self._street_of(case.driver_id)
            first = first_name(d.name)
            ev = await self._send(d, "driver", "voice", opening_line(first, street), case.id,
                                  variables=call_variables(d.name, street, case.depth_in))
            call_id = ev.get("call_id")
            if call_id:
                self._spawn(self._watch_call(case.id, str(call_id)))
            return self._note(case, elapsed, f"Voice call to driver ({ev['mode']}, {ev['status']}): no answer yet")
        if kind == "contact_family":
            body = (f"State Farm Flood Watch: {d.name}'s car has stopped in floodwater near "
                    f"{case.location.lat:.4f}, {case.location.lon:.4f} and they haven't answered. Responders are "
                    f"being notified. Reply SAFE if you've reached them.")
            ev, _ = await asyncio.gather(
                self._send(d, "emergency_contact", "text", body, case.id),
                self._send(d, "emergency_contact", "voice", f"This is State Farm Flood Watch calling about {d.name}.", case.id),
            )
            return self._note(case, elapsed, f"Text + call to emergency contact ({ev['mode']}, {ev['status']})")
        if kind == "dispatch_drone":
            dcfg = settings()["drone"]
            cap = float(dcfg["demo_max_flight_s"]) if self.profile == "demo" else None
            drone = dispatch.launch(case.id, dcfg["station"], case.location.lat, case.location.lon, e.t_sim_s,
                                    float(dcfg["speed_mps"]), cap)
            self.world.drones[case.id] = drone
            return self._note(case, elapsed, f"Drone launched from {dcfg['station']['name']}, ETA {drone.flight_s:.0f} s (simulated)")
        return case

    def _note(self, case: Case, t: float, text: str, kind: str = "outreach") -> Case:
        entry = TimelineEntry(ts=now_iso(), t_case_s=round(t, 1), kind=kind, text=text)
        return case.model_copy(update={"timeline": [*case.timeline, entry]})

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    def _street_of(self, driver_id: str) -> str:
        m = self.world.motions.get(driver_id)
        return self.engine.town.segment_name(current_edge(m, self.lengths)) if m else "your location"

    # ---- post-call memory: voice call result -> case + text follow-up ----
    async def _poll_conversation(self, call_id: str) -> dict[str, Any] | None:
        deadline = time.monotonic() + CALL_WATCH_MAX_S
        while True:
            conv = await voice_elevenlabs.get_conversation(call_id)
            if conv and conv.get("status") in CALL_DONE_STATUSES:
                return conv
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(CALL_POLL_INTERVAL_S)

    async def _watch_call(self, case_id: str, call_id: str) -> None:
        """Wait for the call to end, record it on the case, apply the driver's answer, then text a follow-up."""
        world = self.world
        try:
            conv = await self._poll_conversation(call_id)
            if conv is None or self.world is not world:
                return
            case = world.cases.get(case_id)
            if case is None:
                return
            outcome = classify_call(conv)
            elapsed = self.engine.t_sim_s - world.case_opened_s[case_id]
            world.cases[case_id] = self._note(case, elapsed, f"Call summary: {outcome.summary}", kind="call")
            await self.engine.emit("case.update", world.cases[case_id].model_dump(mode="json"))
            if outcome.reply:
                await self.reply(case_id, outcome.reply, "driver")
            if self.world is not world:
                return
            d = self.drivers[world.cases[case_id].driver_id]
            await self._send(d, "driver", "text", follow_up_text(outcome, self._street_of(d.id)), case_id)
        except Exception:  # never raise out of a background task
            log.exception("call watcher failed for %s", case_id)

    async def reply(self, case_id: str, kind: Literal["safe", "need_help"],
                    by: Literal["driver", "emergency_contact"] = "driver") -> Case | None:
        case = self.world.cases.get(case_id)
        if not case:
            return None
        elapsed = self.engine.t_sim_s - self.world.case_opened_s[case_id]
        new = esc.transition(case, esc.Reply(kind, by, round(elapsed, 1)), now_iso())
        if new.state == "resolved" and case_id in self.world.drones:
            drone = self.world.drones.pop(case_id)
            await self.engine.emit("drone.update", {**dispatch.state(drone, self.engine.t_sim_s), "status": "returning"})
        self.world.cases[case_id] = new
        await self.engine.emit("case.update", new.model_dump(mode="json"))
        return new

    # ---- drones ---------------------------------------------------------
    async def drone_hook(self, e: Engine) -> None:
        world = self.world
        for cid, drone in list(world.drones.items()):
            await e.emit("drone.update", dispatch.state(drone, e.t_sim_s))
            case = world.cases.get(cid)
            if case is None or self.world is not world:
                return
            if dispatch.arrived(drone, e.t_sim_s) and case.state == "drone_en_route":
                await self._drone_arrived(e, case, drone)

    async def _drone_arrived(self, e: Engine, case: Case, drone: dispatch.Drone) -> None:
        d = self.drivers[case.driver_id]
        vision, people = result_for(night=self._hour(d) == NIGHT_HOUR, recommendation="boat_required")
        observed_in = WATER_LEVEL_IN.get(vision.get("water_level", "none"), 0.0) if vision else 0.0
        at_car_in = max(case.depth_in, observed_in)  # the drone's eyes beat the model's estimate
        boat_in = float(settings()["road_status_in"]["boat"])
        boat = at_car_in >= boat_in or not self._truck_route_exists(e, case)
        if vision:
            vision = {**vision, "recommendation": "boat_required" if boat else "truck_route_available"}
        elapsed = round(e.t_sim_s - self.world.case_opened_s[case.id], 1)
        vr = VisionResult(**vision) if vision else None
        new = esc.transition(case, esc.DroneArrived(vr, people, elapsed), now_iso())
        self.world.cases[case.id] = new
        await e.emit("case.update", new.model_dump(mode="json"))

    def _truck_route_exists(self, e: Engine, case: Case) -> bool:
        st = settings()["drone"]["station"]
        town = e.town
        dists = [(dispatch.distance_m(st["lat"], st["lon"], dat["y"], dat["x"]), n) for n, dat in town.graph.nodes(data=True)]
        src = min(dists)[1]
        m = self.world.motions.get(case.driver_id)
        if m is None:
            return False
        dst = edge_end(current_edge(m, self.lengths))
        boat_only = {eid for eid, s in e.statuses.items() if s == "boat"} - {current_edge(m, self.lengths)}
        return dry_route(town.graph, src, dst, boat_only, "truck") is not None

    # ---- counters -------------------------------------------------------
    def counters(self) -> dict[str, int]:
        w = self.world
        stopped = len(w.cases)
        verified = sum(len(c.vision.people) if c.vision else 0 for c in w.cases.values())
        claims = settings()["claims"]
        warned = {d for d, _ in w.warned if w.pretrip_cards.get(d, {}).get("blocking")}
        protected = warned | w.rerouted  # unique drivers kept off a closed road
        estimate = int(len(protected) * claims["avg_vehicle_claim_usd"] * claims["share_would_have_entered_water"])
        return {"drivers_warned": len({d for d, _ in w.warned}), "drivers_rerouted": len(w.rerouted),
                "cars_stopped_in_water": stopped, "people_verified": verified,
                "est_claims_avoided_usd": estimate}

    async def counters_hook(self, e: Engine) -> None:
        c = self.counters()
        if c != self.world.last_counters:
            self.world.last_counters = c
            await e.emit("counters", c)
