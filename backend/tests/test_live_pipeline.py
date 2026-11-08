"""Live demo pipeline for the phone-app user hc-dana (HITIDE_LIVE_USERS): replay crest -> pin -> real (faked)
ElevenLabs call -> "No" -> need help + responders flagged. Everyone else stays mock. No network: every sender is faked."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

import pytest
from fastapi.testclient import TestClient

from sim.region_flood import epoch

pytest.importorskip("osmnx")

DANA_PHONE = "+15550100123"
RUTH_PHONE = "+15550100999"
PARK_ST = {"lat": 30.03785, "lon": -99.13361}   # cp-0043, Park Street over Quinlan Creek: confirmed flooded by 05:00
CREST = "07:20"
STEP_MIN = 5   # the loop's belief is stateful: step it like the replay does, not just once at the crest
WATCH_WAIT_S = 10.0


@dataclass(frozen=True)
class FakeCallResult:
    status: Literal["sent", "failed"]
    conversation_id: str | None


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("live")
    mp = pytest.MonkeyPatch()
    mp.setenv("PHOTON_MODE", "mock")
    mp.setenv("EVIDENCE_POLL_SECONDS", "0")
    mp.setenv("HITIDE_DB_BACKEND", "sqlite")
    mp.setenv("SAFETY_REGISTRY_PATH", str(tmp / "registry.json"))
    mp.setenv("SAFETY_STATE_PATH", str(tmp / "state.json"))
    from app.main import app

    with TestClient(app) as c:
        yield c
    mp.undo()


def _hill(client):
    from app.hill_runtime import get_hill
    return client.portal.call(get_hill, client.app)


@pytest.fixture(scope="module")
def crest(client):
    """Replay from midnight to the crest (no outreach on the way), so cp-0043 is confirmed flooded."""
    h = _hill(client)
    client.portal.call(h.safety.after_step, h.loop)   # make sure the region is built
    h.safety.reset("replay")
    for m in range(0, 7 * 60 + 20 + 1, STEP_MIN):
        h.loop.step(epoch(f"2025-07-04T{m // 60:02d}:{m % 60:02d}:00-05:00"))
    assert h.loop.status.get("cp-0043") == "confirmed_flooded"
    from safety.context import build_context
    h.safety.refresh(build_context(h.loop))   # assess everyone at the crest without dispatching any outreach
    return h


@pytest.fixture
def sent(monkeypatch) -> list[tuple]:
    """Live env for Dana + fakes for every real sender. Returns what would have gone out."""
    import safety.monitor as monitor_mod
    from outreach import photon2, photon_spectrum, voice_elevenlabs

    calls: list[tuple] = []

    async def p2_text(handle, text, *, transport=None):
        calls.append(("text", handle, text))
        return "sent"

    async def p2_poll(handle, q, options, *, transport=None):
        calls.append(("poll", handle, q))
        return "sent"

    async def place_call(to, first_message, variables=None, *, transport=None):
        calls.append(("call", to, first_message))
        return FakeCallResult("sent", f"conv_{len(calls)}")

    async def get_conversation(conversation_id, *, transport=None):
        return {"status": "done", "analysis": {"transcript_summary": "Driver said no."},
                "transcript": [{"role": "agent", "message": "Are you okay?"}, {"role": "user", "message": "No"}]}

    monkeypatch.setattr(photon2, "send_text", p2_text)
    monkeypatch.setattr(photon2, "send_poll", p2_poll)
    monkeypatch.setattr(photon_spectrum, "send_text", p2_text)
    monkeypatch.setattr(photon_spectrum, "send_poll", p2_poll)
    monkeypatch.setattr(voice_elevenlabs, "place_call", place_call)
    monkeypatch.setattr(voice_elevenlabs, "get_conversation", get_conversation)
    monkeypatch.setattr(monitor_mod, "CALL_POLL_S", 0.01)
    for k, v in {"ELEVENLABS_API_KEY": "k", "ELEVENLABS_AGENT_ID": "a", "ELEVENLABS_PHONE_NUMBER_ID": "p"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("HITIDE_LIVE_PROVIDER", raising=False)
    monkeypatch.delenv("SPECTRUM_PROJECT_ID", raising=False)
    monkeypatch.delenv("SAFETY_API_KEY", raising=False)
    monkeypatch.setenv("PHOTON_MODE", "mock")
    monkeypatch.setenv("HITIDE_LIVE_USERS", "hc-dana")
    monkeypatch.setenv("DEMO_PHONE_DANA", DANA_PHONE)
    monkeypatch.setenv("DEMO_PHONE_B", RUTH_PHONE)
    return calls


def _to(calls: list[tuple], phone: str) -> list[tuple]:
    return [c for c in calls if c[1] == phone]


def _at_risk(client, uid: str) -> dict | None:
    rows = client.get("/api/users/at-risk?min_level=warning&limit=2000").json()["users"]
    return next((r for r in rows if r["user_id"] == uid), None)


def test_reset_clears_one_users_track(client, crest, sent):
    client.post("/api/users/hc-dana/location", json={**PARK_ST, "speed_mps": 0})
    assert _at_risk(client, "hc-dana") is not None
    r = client.post("/api/users/hc-dana/reset")
    assert r.status_code == 200 and r.json() == {"user_id": "hc-dana", "reset": True}
    assert _at_risk(client, "hc-dana") is None and crest.safety.response("hc-dana").need_help is False
    assert client.post("/api/users/nobody/reset").status_code == 404
    assert client.post("/api/users/hc-dana/reset", headers={"origin": "https://evil.invalid"}).status_code == 403


def test_reset_requires_api_key_when_set(client, crest, sent, monkeypatch):
    monkeypatch.setenv("SAFETY_API_KEY", "k3y")
    assert client.post("/api/users/hc-dana/reset").status_code == 401
    assert client.post("/api/users/hc-dana/reset", headers={"x-safety-key": "k3y"}).status_code == 200


def test_warning_at_home_sends_dana_a_real_text(client, crest, sent):
    client.post("/api/users/hc-dana/reset")
    client.portal.call(crest.safety.after_step, crest.loop)
    assert crest.safety.assessment("hc-dana").level.label == "warning"
    texts = [c for c in _to(sent, DANA_PHONE) if c[0] == "text"]
    assert len(texts) == 1
    body = texts[0][2]
    assert body.startswith("HiTide:") and "If you see water on the road, turn around." in body


def test_stopped_on_flooded_crossing_calls_dana_and_no_means_help(client, crest, sent):
    client.post("/api/users/hc-dana/reset")
    r = client.post("/api/users/hc-dana/location", json={**PARK_ST, "speed_mps": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["level"] == "critical" and any(a["template"] == "critical_call" for a in body["actions"])
    calls = [c for c in _to(sent, DANA_PHONE) if c[0] == "call"]
    assert len(calls) == 1
    deadline = time.monotonic() + WATCH_WAIT_S
    row = _at_risk(client, "hc-dana")
    while not (row and row["response"]["need_help"]) and time.monotonic() < deadline:
        time.sleep(0.05)
        row = _at_risk(client, "hc-dana")
    assert row is not None
    assert row["response"]["need_help"] is True and row["response"]["responders_flagged"] is True
    assert "+1555" not in str(row)


def test_repeat_pin_after_reset_calls_again(client, crest, sent):
    for _ in range(2):
        client.post("/api/users/hc-dana/reset")
        client.post("/api/users/hc-dana/location", json={**PARK_ST, "speed_mps": 0})
    assert len([c for c in _to(sent, DANA_PHONE) if c[0] == "call"]) == 2


def test_ruth_stays_mock_with_the_same_env(client, crest, sent):
    client.post("/api/users/hc-ruth/reset")
    r = client.post("/api/users/hc-ruth/location", json={**PARK_ST, "speed_mps": 0})
    assert r.json()["level"] == "critical" and any(a["kind"] == "voice" for a in r.json()["actions"])
    client.portal.call(crest.safety.after_step, crest.loop)
    assert _to(sent, RUTH_PHONE) == []
    assert all(c[1] == DANA_PHONE for c in sent)   # nobody but Dana ever reaches a real sender
