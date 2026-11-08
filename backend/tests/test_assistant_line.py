"""The app's assistant line: context pushed to the agent, number returned, call outcome flags responders."""

import asyncio

import pytest

from safety import assistant as assistant_mod
from safety.assistant import AssistantLine, assistant_variables
from safety.directions import Directions

ASSESSMENT = {"advice": "move_to_high_ground", "reasons": ["Park Street is confirmed flooded where you are"],
              "hazard": {"road_name": "Park Street", "depth_in": None, "max_depth_nearby_in": 14.4}}
DIRECTIONS = Directions("Head for higher ground by Hill Road, about 0.6 km.", ("Hill Road",), 600.0)


class FakeMonitor:
    def __init__(self):
        self.notes: list[str] = []
        self.results: list[tuple] = []
        self.dispatched: list = []
        self.users = {"hc-dana": object(), "hc-ruth": object()}

    def note(self, uid, what):
        self.notes.append(what)

    def call_result(self, uid, answered, reply, by):
        self.results.append((uid, answered, reply, by))
        return ["flag_responders"] if reply == "need_help" else []

    async def dispatch_actions(self, user, acts):
        self.dispatched.extend(acts)


def test_variables_carry_situation_depth_advice_and_directions():
    v = assistant_variables("Dana Whitfield", ASSESSMENT, DIRECTIONS)
    assert v["driver_first_name"] == "Dana" and v["street"] == "Park Street"
    assert v["water_depth_in"] == "14"            # nearby depth when the road itself has no gauge
    assert v["situation"].startswith("Park Street") and "Hill Road" in v["directions"]
    assert v["advice"] and v["call_purpose"] == "assistant"
    assert "phone" not in " ".join(v).lower()


def test_unknown_depth_is_said_as_unknown():
    a = {**ASSESSMENT, "hazard": {"road_name": None, "depth_in": None, "max_depth_nearby_in": None}}
    v = assistant_variables("Dana", a, DIRECTIONS)
    assert v["water_depth_in"] == "unknown" and v["street"] == "an unknown road"


def test_without_the_opt_in_nothing_external_happens(monkeypatch):
    monkeypatch.delenv("HITIDE_ASSISTANT_LIVE", raising=False)
    called = []
    monkeypatch.setattr(assistant_mod.voice_elevenlabs, "set_agent_defaults", lambda *a, **k: called.append(1))
    m = FakeMonitor()
    out = asyncio.run(AssistantLine(m).request("hc-dana", "Dana", ASSESSMENT, DIRECTIONS))
    assert out["mode"] == "mock" and out["phone"] is None and out["directions"]["text"] == DIRECTIONS.text
    assert m.notes == ["assistant call requested (simulated)"] and not called


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv("HITIDE_ASSISTANT_LIVE", "1")
    monkeypatch.delenv("HITIDE_ASSISTANT_NUMBER", raising=False)
    monkeypatch.setattr(assistant_mod.voice_elevenlabs, "voice_configured", lambda: True)
    calls: dict = {"defaults": []}

    async def set_defaults(variables, **_k):
        calls["defaults"].append(dict(variables))
        return True

    async def number(**_k):
        return "+15550100000"

    convs = [{"conversation_id": "old", "start_time_unix_secs": 10.0, "status": "done"},
             {"conversation_id": "c1", "start_time_unix_secs": 1000.0, "status": "done"}]

    async def listing(**_k):
        return list(reversed(convs))

    async def conversation(cid, **_k):
        return {"status": "done", "transcript": [{"role": "user", "message": "I need help, the water is rising"}],
                "analysis": {"transcript_summary": "Caller trapped on Park Street, asked for help."}}

    monkeypatch.setattr(assistant_mod.voice_elevenlabs, "set_agent_defaults", set_defaults)
    monkeypatch.setattr(assistant_mod.voice_elevenlabs, "agent_phone_number", number)
    monkeypatch.setattr(assistant_mod.voice_elevenlabs, "list_conversations", listing)
    monkeypatch.setattr(assistant_mod.voice_elevenlabs, "get_conversation", conversation)
    return calls


def test_live_pushes_context_returns_the_number_and_a_help_call_flags_responders(live):
    m = FakeMonitor()
    emitted = []

    async def emit(typ, payload):
        emitted.append((typ, payload))

    async def run():
        line = AssistantLine(m, emit, poll_s=0.01, max_s=2, clock=lambda: 990.0)
        out = await line.request("hc-dana", "Dana Whitfield", ASSESSMENT, DIRECTIONS)
        await asyncio.wait_for(asyncio.gather(*line._watchers.values()), 2)
        return out

    out = asyncio.run(run())
    assert out["mode"] == "live" and out["phone"] == "+15550100000"
    session, reset = live["defaults"]
    assert session["street"] == "Park Street" and "Hill Road" in session["directions"]
    assert reset == dict(assistant_mod.NEUTRAL)   # after the call nobody else hears Dana's street
    assert m.notes[0] == "assistant call requested" and m.notes[-1].startswith("assistant call: Caller trapped")
    assert m.results == [("hc-dana", True, "need_help", "driver")] and m.dispatched == ["flag_responders"]
    assert emitted[0][0] == "user.call" and emitted[0][1]["recipient"] == "assistant"


def test_an_env_number_wins_and_a_missing_number_is_reported(live, monkeypatch):
    monkeypatch.setenv("HITIDE_ASSISTANT_NUMBER", "+15550199999")
    m = FakeMonitor()

    async def run(line):
        out = await line.request("hc-dana", "Dana", ASSESSMENT, DIRECTIONS)
        for t in list(line._watchers.values()):
            t.cancel()
        return out

    assert asyncio.run(run(AssistantLine(m, poll_s=0.01, max_s=0.05)))["phone"] == "+15550199999"
    monkeypatch.delenv("HITIDE_ASSISTANT_NUMBER")

    async def none(**_k):
        return None

    monkeypatch.setattr(assistant_mod.voice_elevenlabs, "agent_phone_number", none)
    m2 = FakeMonitor()
    out = asyncio.run(AssistantLine(m2).request("hc-dana", "Dana", ASSESSMENT, DIRECTIONS))
    assert out["mode"] == "unavailable" and out["phone"] is None and m2.notes == ["assistant line unavailable"]


def test_calls_that_started_before_the_tap_are_ignored(live, monkeypatch):
    async def listing(**_k):
        return [{"conversation_id": "old", "start_time_unix_secs": 10.0, "status": "done"}]

    monkeypatch.setattr(assistant_mod.voice_elevenlabs, "list_conversations", listing)
    m = FakeMonitor()

    async def run():
        line = AssistantLine(m, poll_s=0.01, max_s=0.05, clock=lambda: 990.0)
        await line.request("hc-dana", "Dana", ASSESSMENT, DIRECTIONS)
        await asyncio.gather(*line._watchers.values())

    asyncio.run(run())
    assert m.notes[-1] == "assistant call not detected" and not m.results


def test_one_session_at_a_time_cooldown_and_each_call_claimed_once(live):
    m = FakeMonitor()

    async def run():
        line = AssistantLine(m, poll_s=0.01, max_s=0.5, clock=lambda: 990.0)
        a = await line.request("hc-dana", "Dana", ASSESSMENT, DIRECTIONS)
        again = await line.request("hc-dana", "Dana", ASSESSMENT, DIRECTIONS)   # within the cooldown
        assert again["phone"] == a["phone"] and len(live["defaults"]) == 1
        await line.request("hc-ruth", "Ruth", ASSESSMENT, DIRECTIONS)          # replaces Dana's session
        assert list(line._watchers) == ["hc-ruth"]
        await asyncio.gather(*line._watchers.values(), return_exceptions=True)
        return line

    line = asyncio.run(run())
    assert line._claimed == {"c1"}          # the one new inbound call, attributed once
    assert m.results == [("hc-ruth", True, "need_help", "driver")]


def test_outbound_calls_and_bad_numbers_are_never_used(live, monkeypatch):
    async def outbound(**_k):
        return [{"conversation_id": "o1", "start_time_unix_secs": 1000.0, "status": "done", "direction": "outbound"}]

    async def bad_number(**_k):
        return "javascript:alert(1)"

    monkeypatch.setattr(assistant_mod.voice_elevenlabs, "list_conversations", outbound)
    m = FakeMonitor()

    async def run():
        line = AssistantLine(m, poll_s=0.01, max_s=0.05, clock=lambda: 990.0)
        await line.request("hc-dana", "Dana", ASSESSMENT, DIRECTIONS)
        await asyncio.gather(*line._watchers.values())

    asyncio.run(run())
    assert not m.results and m.notes[-1] == "assistant call not detected"
    monkeypatch.setattr(assistant_mod.voice_elevenlabs, "agent_phone_number", bad_number)
    out = asyncio.run(AssistantLine(FakeMonitor()).request("hc-dana", "Dana", ASSESSMENT, DIRECTIONS))
    assert out["mode"] == "unavailable" and out["phone"] is None

