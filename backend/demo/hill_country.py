"""Scripted Hill Country demo: replay July 4, 2025, 01:00 -> 07:30 CDT, about 150x (overview.md 20).

Real: OSM roads, USGS 3DEP terrain, USGS gauge readings (incl. the Hunt gauge dying at 05:10 CDT), and the
NWS warning timeline. Simulated: households, drone flights, snapshots (from the replay truth), outreach.
Beats are detected from the loop's state, not hard-coded times, so the run follows the data.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from critical.loop import CriticalLoop, iso
from outreach.base import Channel, OutboundMessage
from routing.instructions import TURN_AROUND, route_message, route_out, shelter_message
from sim.region_flood import epoch

log = logging.getLogger(__name__)
Emit = Callable[[str, dict[str, Any]], Awaitable[None]]

DEFAULT_SPEED = 150.0       # sim seconds per real second
TICK_REAL_S = 0.5
FAMILY_DELAY_REAL_S = 15.0  # no answer from B -> call + text the emergency contact
HUNT_GAUGE = "08165500"
PERSONAS = {
    "A": {"driver_id": "hc-a", "first": "Teammate A", "phone": "env:DEMO_PHONE_A"},
    "B": {"driver_id": "hc-b", "first": "Ruth", "phone": "env:DEMO_PHONE_B"},       # older resident, simulated
    "C": {"driver_id": "hc-b", "first": "Teammate C", "phone": "env:DEMO_PHONE_C"},  # B's emergency contact
}


def _log_failure(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.error("hill country replay crashed", exc_info=task.exception())


class HillCountryDemo:
    def __init__(self, loop: CriticalLoop, emit: Emit, outreach: Any):
        self.loop, self.emit, self.outreach = loop, emit, outreach
        self.task: asyncio.Task | None = None
        self.speed = DEFAULT_SPEED
        self.t: float | None = None
        self.running = False
        self.beats: set[int] = set()
        self.sent: dict[str, dict] = {}
        self.background: set[asyncio.Task] = set()

    # ---- control --------------------------------------------------------
    def start(self, speed: float = DEFAULT_SPEED) -> None:
        self.cancel()
        self.speed = speed
        self.task = asyncio.create_task(self._run())
        self.task.add_done_callback(_log_failure)

    def cancel(self) -> None:
        for t in [self.task, *self.background]:
            if t and not t.done():
                t.cancel()
        self.background.clear()
        self.running = False

    def reset(self) -> None:
        self.cancel()
        self._clear()

    def _clear(self) -> None:
        self.loop.reset_state()
        self.t, self.beats, self.sent = None, set(), {}

    # ---- run ------------------------------------------------------------
    async def _beat(self, n: int, title: str, detail: str) -> None:
        if n in self.beats:
            return
        self.beats.add(n)
        log.info("hill country beat %d: %s", n, title)
        await self.emit("demo.step", {"scenario": "hill_country", "step": n, "title": title, "detail": detail,
                                      "sim_time": iso(self.t or 0)})

    async def _run(self) -> None:
        replay = self.loop.region.cfg["replay"]
        start, end = epoch(replay["start_local"]), epoch(replay["end_local"])
        self._clear()  # not reset(): that cancels the task we are running in
        self.running = True
        self.t = start
        await self.emit("region.reset", {"scenario": "hill_country", "sim_time": iso(start)})
        real0 = time.monotonic()
        try:
            while self.t <= end:
                events = await asyncio.to_thread(self.loop.step, self.t)
                for typ, payload in events:
                    await self.emit(typ, {"scenario": "hill_country", **payload})
                await self.emit("region.counters", {"scenario": "hill_country", "sim_time": iso(self.t), **self.loop.counters()})
                await self._beats(events)
                await asyncio.sleep(TICK_REAL_S)
                self.t = start + (time.monotonic() - real0) * self.speed  # wall clock: a slow step = bigger dt
            await self._beat(7, "Counters", "Households warned, routes sent, communities cut off, crossings checked by drone.")
        finally:
            self.running = False

    async def _beats(self, events: list[tuple[str, dict]]) -> None:
        loop = self.loop
        types = {t for t, _ in events}
        if loop.alerts:
            await self._beat(1, "Flash Flood Warning, Kerr County (real, 01:14 CDT)",
                             "Replay of July 4, 2025. Crossings near the forks turn unknown; there is no gauge on the South Fork.")
        if loop.alerts and loop.ranked:
            top = loop.ranked[0]
            p = loop.points[top.point_id]
            single = next((b for b in loop.ranked
                           if any(b.point_id in loop.node_state[n].unavoidable for n in b.node_ids)), None)
            extra = ""
            if single and single.point_id != top.point_id:
                sp = loop.points[single.point_id]
                extra = f" Top single way out: {sp['name']} over {sp['waterway']} ({int(single.dependency)} households have no other exit)."
            await self._beat(2, f"Critical point #1: {p['name']} over {p['waterway']}",
                             f"Priority {top.priority:.0f} = dependency {top.dependency:.0f} x vulnerability {top.vulnerability:.2f} "
                             f"x (0.5+p) {top.p_weight:.2f} x uncertainty {top.uncertainty:.2f} x urgency {top.urgency:g}.{extra} "
                             "Drones go only where a flight changes what we tell people.")
        wet = [p for t, p in events if t == "snapshot.created" and p["water_on_road"]]
        if wet:
            p = loop.points[wet[0]["point_id"]]
            await self._beat(3, f"Drone confirms water on {p['name']}",
                             f"About {wet[0]['est_depth_in']:.0f} in over the road (simulated snapshot). The map and every route update.")
        cut = [nid for nid, st in loop.node_state.items() if st.status == "cut_off" and st.instruction == "shelter_in_place"]
        if cut:
            best = max(cut, key=lambda nid: (loop.nodes[nid]["kind"] != "homes", loop.nodes[nid]["households"]))
            n, st = loop.nodes[best], loop.node_state[best]
            await self._beat(4, f"{n['name']} is cut off: shelter in place",
                             f"Every exit is flooded. Responders flagged: {'boat required' if st.rescue == 'boat_required' else 'a high-clearance truck can still get in'}. "
                             "The next flight checks the rescue approach.")
        if "gauge.status" in types and not loop.gauges_online.get(HUNT_GAUGE, True):
            await self._beat(5, "The Hunt gauge goes dark (real: last reading 05:10 CDT)",
                             "Its last reading was a record 37.52 ft; after 30 min of silence it counts as offline. "
                             "Downstream uncertainty jumps and the drones re-plan.")
        await self._outreach()

    # ---- persona outreach (overview 20, step 5-7) -------------------------
    async def _outreach(self) -> None:
        loop = self.loop
        names = {e: p["name"] for p in loop.points.values() for e in p["edge_ids"]}
        names.update({f["properties"]["edge_id"]: f["properties"]["name"] for f in loop.region.segments_fc["features"]})
        if "A" not in self.sent:
            nid = next((n for n, st in loop.node_state.items()
                        if st.instruction == "route_out" and loop.nodes[n]["town"] == "Kerrville"), None)
            if nid:
                route = route_out(loop.graph, loop.nodes[nid]["road_node"], loop.safe, loop.point_of, loop.status, names)
                if route:
                    self.sent["A"] = {"node": nid}
                    await self._send("A", "poll", route_message(loop.nodes[nid]["name"], route), ("I'm safe", "I need help", "I've left"))
                    await self._beat(6, "Instructions go out", "Kerrville subdivision: a route out by text with a poll. "
                                     "A cut-off older resident: a voice call to shelter in place. Then her daughter.")
        if "B" not in self.sent:
            nid = next((n for n, st in loop.node_state.items() if st.instruction == "shelter_in_place"
                        and loop.nodes[n]["kind"] == "homes" and loop.nodes[n]["town"] in ("Hunt", "Ingram")), None)
            if nid:
                self.sent["B"] = {"node": nid}
                await self._send("B", "voice", shelter_message(PERSONAS["B"]["first"]))
                task = asyncio.create_task(self._family(nid))
                self.background.add(task)
                task.add_done_callback(self.background.discard)

    async def _family(self, nid: str) -> None:
        await asyncio.sleep(FAMILY_DELAY_REAL_S)
        n = self.loop.nodes[nid]
        body = (f"State Farm Flood Watch: your mother's area ({n['town']}) is cut off by floodwater and she is not answering. "
                f"We told her to go to high ground and flagged responders. Can you reach her? Do not drive there. {TURN_AROUND}")
        self.sent["C"] = {"node": nid}
        await self._send("C", "text", body)
        await self._send("C", "voice", f"Hi, this is State Farm Flood Watch about Ruth in {n['town']}. Her roads are flooded and "
                                       "she has not answered. Responders know where she is. Can you reach her?")

    async def _send(self, who: str, channel: Channel, body: str, options: tuple[str, ...] = ()) -> None:
        p = PERSONAS[who]
        recipient = "emergency_contact" if who == "C" else "driver"
        node = self.loop.nodes.get(self.sent.get(who, {}).get("node", ""), {})
        variables = {"driver_first_name": PERSONAS["B"]["first"] if who == "C" else p["first"],
                     "street": f"your road in {node.get('town', 'Kerr County')}", "water_depth_in": "12",
                     "call_purpose": "family" if who == "C" else "driver"}  # every {{var}} the agent prompt uses
        msg = OutboundMessage(driver_id=p["driver_id"], recipient=recipient, channel=channel, body=body, phone=p["phone"],
                              poll_options=options, variables=variables)
        try:
            await self.outreach.send(msg)
        except Exception:  # outreach must never stop the replay
            log.exception("hill country outreach to %s failed", who)
