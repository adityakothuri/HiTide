"""Runner wiring for context-aware voice calls: call variables, post-call watcher, text follow-up."""

from __future__ import annotations

import asyncio
import dataclasses
import re

import pytest

from demo.scenario import DemoScenario
from outreach import OutboundMessage
from outreach.call_summary import CallOutcome
from sim.drivers import load_drivers
from sim.engine import Engine
from sim.town import load_town
from stages import runner as runner_mod
from stages.runner import StageRunner

PHONE = re.compile(r"\+1\d{10}|830555\d{4}")
HAS_VARIABLES = "variables" in {f.name for f in dataclasses.fields(OutboundMessage)}


class FakeOutreach:
    def __init__(self, call_id: str | None = None) -> None:
        self.sent: list[OutboundMessage] = []
        self.call_id = call_id

    async def send(self, msg: OutboundMessage) -> dict:
        self.sent.append(msg)
        ev = {"mode": "mock", "status": "sent", "channel": msg.channel}
        if msg.channel == "voice" and self.call_id:
            ev["call_id"] = self.call_id
        return ev


@pytest.fixture
def staged(monkeypatch):
    """Runner with a stalled demo-d case open and a recording fake outreach."""
    monkeypatch.setattr(runner_mod, "CALL_POLL_INTERVAL_S", 0.0)

    async def build():
        events: list[tuple[str, dict]] = []

        async def emit(t: str, p: dict) -> None:
            events.append((t, p))

        town, drivers = load_town(), load_drivers()
        eng = Engine(town=town, drivers=drivers, emit=emit, speed=1.0)
        runner = StageRunner(eng, drivers)
        runner.outreach = FakeOutreach(call_id=None)  # no watcher spawns while staging
        demo = DemoScenario(eng, runner)
        runner.world.suppress_pretrip.update({"demo-b", "demo-d"})
        await eng.begin_flood(__import__("demo.scenario", fromlist=["SIM_ALERT"]).SIM_ALERT)
        for _ in range(40):
            await eng.step(60)
        runner.world.motions["demo-d"] = demo._stall_d()
        for _ in range(60):
            await eng.step(1)
            if "demo-d" in runner.world.case_by_driver:
                break
        return runner, events

    return build


def _conv(status: str, user: str | None = None, driver_status: str | None = None) -> dict:
    tr = [{"role": "agent", "message": "Are you safe?"}]
    if user:
        tr.append({"role": "user", "message": user})
    analysis: dict = {"transcript_summary": "Driver reported status."}
    if driver_status:
        analysis["data_collection_results"] = {"driver_status": {"value": driver_status}}
    return {"status": status, "transcript": tr, "analysis": analysis, "metadata": {}}


def _patch_conversations(monkeypatch, seq: list[dict | None]) -> list[int]:
    calls: list[int] = []

    async def fake(cid: str, *, transport=None):
        calls.append(1)
        return seq[min(len(calls) - 1, len(seq) - 1)]

    monkeypatch.setattr(runner_mod.voice_elevenlabs, "get_conversation", fake)
    return calls


def test_street_and_first_name_helpers_via_call_driver(staged):
    async def go():
        runner, _ = await staged()
        cid = runner.world.case_by_driver["demo-d"]
        runner.outreach.sent.clear()
        runner.outreach.call_id = "conv_1"
        started: list[tuple] = []

        async def fake_watch(case_id, call_id):
            started.append((case_id, call_id))

        runner._watch_call = fake_watch  # type: ignore[method-assign]
        case = runner.world.cases[cid]
        new = await runner._timer_action(runner.engine, case, "call_driver", 12.0)
        await asyncio.gather(*runner._pending)
        return runner, cid, new, started

    runner, cid, new, started = asyncio.run(go())
    voice = [m for m in runner.outreach.sent if m.channel == "voice"][0]
    first = runner.drivers["demo-d"].name.split()[0]
    assert voice.body.startswith(f"Hi {first}, this is State Farm Flood Watch.")
    assert voice.body.endswith("Are you safe?")
    if HAS_VARIABLES:
        assert set(voice.variables) == {"driver_first_name", "street", "water_depth_in"}
        assert voice.variables["driver_first_name"] == first
    assert started == [(cid, "conv_1")]
    assert not PHONE.search(new.timeline[-1].text)


def test_no_call_id_means_no_watcher(staged):
    async def go():
        runner, _ = await staged()
        runner.outreach = FakeOutreach(call_id=None)
        cid = runner.world.case_by_driver["demo-d"]
        runner._watch_call = lambda *a: (_ for _ in ()).throw(AssertionError("no"))  # type: ignore[method-assign]
        await runner._timer_action(runner.engine, runner.world.cases[cid], "call_driver", 5.0)
        return runner

    assert not asyncio.run(go())._pending


@pytest.mark.parametrize("reply,state", [("safe", "resolved"), ("need_help", None)])
def test_watch_call_applies_reply_and_texts_followup(staged, monkeypatch, reply, state):
    calls = _patch_conversations(monkeypatch, [_conv("in-progress"), _conv("done", "ok", reply)])

    async def go():
        runner, _ = await staged()
        cid = runner.world.case_by_driver["demo-d"]
        runner.outreach.sent.clear()
        await runner._watch_call(cid, "conv_1")
        return runner, cid

    runner, cid = asyncio.run(go())
    case = runner.world.cases[cid]
    assert len(calls) == 2  # polled until done
    call_entries = [t for t in case.timeline if t.kind == "call"]
    assert len(call_entries) == 1 and not PHONE.search(call_entries[0].text)
    if state:
        assert case.state == state
    else:
        assert case.state != "resolved" and case.responder_flag
    texts = [m for m in runner.outreach.sent if m.channel == "text" and m.recipient == "driver"]
    assert len(texts) == 1 and "Following up on our call" in texts[0].body


def test_watch_call_unanswered_adds_entry_without_reply(staged, monkeypatch):
    _patch_conversations(monkeypatch, [_conv("failed")])

    async def go():
        runner, _ = await staged()
        cid = runner.world.case_by_driver["demo-d"]
        before = runner.world.cases[cid].state
        await runner._watch_call(cid, "conv_1")
        return runner, cid, before

    runner, cid, before = asyncio.run(go())
    case = runner.world.cases[cid]
    assert case.state == before
    assert [t.kind for t in case.timeline].count("call") == 1


def test_watch_call_times_out_and_never_raises(staged, monkeypatch):
    calls = _patch_conversations(monkeypatch, [None])
    monkeypatch.setattr(runner_mod, "CALL_WATCH_MAX_S", 0.0)

    async def go():
        runner, _ = await staged()
        cid = runner.world.case_by_driver["demo-d"]
        await runner._watch_call(cid, "conv_1")
        return runner, cid

    runner, cid = asyncio.run(go())
    assert calls  # tried at least once
    assert not [t for t in runner.world.cases[cid].timeline if t.kind == "call"]


def test_watch_call_stops_after_world_reset(staged, monkeypatch):
    async def fake(cid: str, *, transport=None):
        runner_ref[0].reset()
        return _conv("done", "help", "need_help")

    runner_ref: list[StageRunner] = []
    monkeypatch.setattr(runner_mod.voice_elevenlabs, "get_conversation", fake)

    async def go():
        runner, _ = await staged()
        runner_ref.append(runner)
        cid = runner.world.case_by_driver["demo-d"]
        runner.outreach.sent.clear()
        await runner._watch_call(cid, "conv_1")
        return runner

    runner = asyncio.run(go())
    assert runner.outreach.sent == [] and runner.world.cases == {}


def test_watch_call_survives_get_conversation_exception(staged, monkeypatch):
    async def boom(cid: str, *, transport=None):
        raise RuntimeError("x")

    monkeypatch.setattr(runner_mod.voice_elevenlabs, "get_conversation", boom)
    monkeypatch.setattr(runner_mod, "CALL_WATCH_MAX_S", 0.0)

    async def go():
        runner, _ = await staged()
        await runner._watch_call(runner.world.case_by_driver["demo-d"], "conv_1")

    asyncio.run(go())


def test_outcome_type_exported():
    assert CallOutcome(None, "", False).answered is False
