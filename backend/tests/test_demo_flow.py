"""End-to-end, headless: drives the real engine + stage runner through the demo, checks every WS event
against the API contract (api/schemas.py) and the privacy rules. Guards the live demo from regressions."""

import json
import re

import pytest

from api import schemas
from demo.scenario import DEMO_FLOOD_MIN, SIM_ALERT, DemoScenario
from sim.drivers import load_drivers
from sim.engine import Engine
from sim.town import load_town
from stages.runner import StageRunner

CONTRACT = {
    "case.update": schemas.Case, "outreach": schemas.OutreachEvent, "turn_around": schemas.TurnAround,
    "reroute": schemas.Reroute, "drone.update": schemas.DroneState, "counters": schemas.Counters,
    "segments.update": schemas.SegmentsUpdate, "drivers.update": schemas.DriversUpdate, "alert": schemas.Alert,
}
PHONE = re.compile(r"\+1\d{10}|830555\d{4}")  # E.164 US or our fake 830-555 numbers (OSM node ids are bare digits)


@pytest.fixture(scope="module")
def world_events():
    import asyncio

    events: list[tuple[str, dict]] = []

    async def emit(type_: str, payload: dict) -> None:
        events.append((type_, payload))

    async def run():
        town, drivers = load_town(), load_drivers()
        eng = Engine(town=town, drivers=drivers, emit=emit, speed=1.0)
        runner = StageRunner(eng, drivers)
        demo = DemoScenario(eng, runner)
        w = runner.world
        w.suppress_pretrip.update({"demo-b", "demo-d"})
        w.motions["demo-b"] = demo._motion("demo-b", 0.0)
        await eng.begin_flood(SIM_ALERT)
        for _ in range(DEMO_FLOOD_MIN):
            await eng.step(60)
        w.motions["demo-b"] = demo._position_b()
        for _ in range(90):
            await eng.step(1)
            if "demo-b" in w.turn_arounds:
                break
        w.motions["demo-d"] = demo._stall_d()
        for _ in range(90):
            await eng.step(1)
            cid = w.case_by_driver.get("demo-d")
            if cid and w.cases[cid].state == "handed_to_responders":
                break
        return runner

    runner = asyncio.run(run())
    return runner, events


def test_pretrip_warns_demo_a_and_teen_parent(world_events):
    runner, events = world_events
    assert ("demo-a", SIM_ALERT["id"]) in runner.world.warned
    assert runner.world.pretrip_cards["demo-a"]["alt_route"] is not None
    sent = [(p["driver_id"], p["recipient"]) for t, p in events if t == "outreach"]
    assert ("demo-t", "parent") in sent


def test_enroute_turn_around_and_reroute_for_b(world_events):
    runner, events = world_events
    ta = runner.world.turn_arounds["demo-b"]
    assert ta["message"] == "Flooded road ahead. Turn around."
    assert any(t == "reroute" and p["driver_id"] == "demo-b" and p["reason"].startswith("Flooded") for t, p in events)
    assert not any(t == "outreach" and p["driver_id"] == "demo-b" and p["channel"] == "text" for t, p in events)


def test_stopped_case_reaches_responders_with_vision(world_events):
    runner, _ = world_events
    case = runner.world.cases[runner.world.case_by_driver["demo-d"]]
    assert case.state == "handed_to_responders"
    assert case.responder_flag is True
    assert case.vision is not None and case.vision.recommendation == "boat_required"
    assert case.responder_view.people_count == 1
    kinds = [e.kind for e in case.timeline]
    assert "flag" in kinds and "vision" in kinds


def test_every_event_matches_the_frontend_contract(world_events):
    _, events = world_events
    for type_, payload in events:
        if type_ in CONTRACT:
            CONTRACT[type_].model_validate(payload)


def test_no_phone_numbers_or_exact_age_in_any_event(world_events):
    _, events = world_events
    blob = json.dumps([p for _, p in events])
    assert not PHONE.search(blob)
    assert "age 78" not in blob and "env:DEMO_PHONE" not in blob


def test_counters_reflect_the_run(world_events):
    runner, _ = world_events
    c = runner.counters()
    assert c["drivers_warned"] >= 2 and c["drivers_rerouted"] >= 1
    assert c["cars_stopped_in_water"] == 1 and c["people_verified"] == 1
