"""Per-user live outreach (HITIDE_LIVE_USERS): listed users get real sends even when PHOTON_MODE is mock."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest

from outreach import make_outreach, photon2, photon_spectrum, voice_elevenlabs
from outreach.base import OutboundMessage
from outreach.live_users import live_provider, live_users

PHONE = "+15550100123"
VOICE_ENV = {"ELEVENLABS_API_KEY": "k", "ELEVENLABS_AGENT_ID": "a", "ELEVENLABS_PHONE_NUMBER_ID": "p"}


@dataclass(frozen=True)
class FakeCallResult:
    status: Literal["sent", "failed"]
    conversation_id: str | None


@pytest.fixture
def sent(monkeypatch) -> list[tuple]:
    calls: list[tuple] = []

    async def p2_text(handle, text, *, transport=None):
        calls.append(("p2_text", handle, text))
        return "sent"

    async def p2_poll(handle, q, options, *, transport=None):
        calls.append(("p2_poll", handle, q))
        return "sent"

    async def st_text(to, body, *, transport=None):
        calls.append(("st_text", to, body))
        return "sent"

    async def place_call(to, first_message, variables=None, *, transport=None):
        calls.append(("call", to, first_message))
        return FakeCallResult("sent", "conv_live")

    monkeypatch.setattr(photon2, "send_text", p2_text)
    monkeypatch.setattr(photon2, "send_poll", p2_poll)
    monkeypatch.setattr(photon_spectrum, "send_text", st_text)
    monkeypatch.setattr(voice_elevenlabs, "place_call", place_call)
    for k in ("SPECTRUM_PROJECT_ID", "SPECTRUM_PROJECT_SECRET", "HITIDE_LIVE_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    for k, v in VOICE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PHOTON_MODE", "mock")
    monkeypatch.setenv("HITIDE_LIVE_USERS", "hc-dana")
    monkeypatch.setenv("DEMO_PHONE_DANA", PHONE)
    monkeypatch.setenv("DEMO_PHONE_B", "+15550100999")
    return calls


async def _noop_emit(_k, _p):
    return None


def _svc(tmp_path: Path, moving: bool = False):
    return make_outreach(_noop_emit, lambda _d: moving, log_path=tmp_path / "log.jsonl")


def _msg(**kw) -> OutboundMessage:
    base = dict(driver_id="hc-dana", recipient="driver", channel="text", body="Flood warning",
                phone="env:DEMO_PHONE_DANA", case_id="c1")
    return OutboundMessage(**{**base, **kw})


# ---- parsing ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw,want", [
    ("", frozenset()), ("hc-dana", frozenset({"hc-dana"})), (" hc-dana , hc-x ,, ", frozenset({"hc-dana", "hc-x"})),
])
def test_live_users_parses_comma_list(monkeypatch, raw, want):
    monkeypatch.setenv("HITIDE_LIVE_USERS", raw)
    assert live_users() == want


def test_live_users_unset_is_empty(monkeypatch):
    monkeypatch.delenv("HITIDE_LIVE_USERS", raising=False)
    assert live_users() == frozenset()


@pytest.mark.parametrize("raw,want", [
    (None, "photon2"), ("photon2", "photon2"), ("stable", "stable"), ("PHOTON", "stable"),
    ("mock", "photon2"), ("bogus", "photon2"),
])
def test_live_provider_is_always_a_live_sender(monkeypatch, raw, want):
    if raw is None:
        monkeypatch.delenv("HITIDE_LIVE_PROVIDER", raising=False)
    else:
        monkeypatch.setenv("HITIDE_LIVE_PROVIDER", raw)
    assert live_provider() == want


# ---- service --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_live_user_gets_real_text_while_mode_is_mock(tmp_path, sent):
    res = await _svc(tmp_path).send(_msg())
    assert sent == [("p2_text", PHONE, "Flood warning")]
    assert res["mode"] == "photon" and res["provider"] == "photon2" and res["status"] == "sent"
    assert PHONE not in str(res) and PHONE not in (tmp_path / "log.jsonl").read_text()


@pytest.mark.asyncio
async def test_live_user_honours_live_provider(tmp_path, sent, monkeypatch):
    monkeypatch.setenv("HITIDE_LIVE_PROVIDER", "stable")
    res = await _svc(tmp_path).send(_msg())
    assert sent == [("st_text", PHONE, "Flood warning")] and res["provider"] == "stable"


@pytest.mark.asyncio
async def test_live_user_voice_places_real_call(tmp_path, sent):
    res = await _svc(tmp_path).send(_msg(channel="voice", body="Are you okay?"))
    assert sent == [("call", PHONE, "Are you okay?")]
    assert res["channel"] == "voice" and res["call_id"] == "conv_live" and res["mode"] == "photon"


@pytest.mark.asyncio
async def test_other_users_stay_mock(tmp_path, sent):
    res = await _svc(tmp_path).send(_msg(driver_id="hc-ruth", phone="env:DEMO_PHONE_B"))
    assert sent == [] and res["mode"] == "mock" and res["status"] == "sent"


@pytest.mark.asyncio
async def test_live_user_still_blocked_while_moving(tmp_path, sent):
    res = await _svc(tmp_path, moving=True).send(_msg())
    assert sent == [] and res["status"] == "blocked"


@pytest.mark.asyncio
async def test_live_user_with_sim_phone_is_suppressed(tmp_path, sent):
    res = await _svc(tmp_path).send(_msg(phone="sim:hc-dana"))
    assert sent == [] and res["status"] == "suppressed"


@pytest.mark.asyncio
async def test_live_user_tts_in_app_stays_mock(tmp_path, sent):
    res = await _svc(tmp_path).send(_msg(channel="tts_in_app"))
    assert sent == [] and res["mode"] == "mock"


# ---- inbound socket ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("mode,users,keys,want", [
    ("photon2", "", True, True),          # unchanged: photon2 mode always listens
    ("mock", "hc-dana", True, True),      # a live demo user's SAFE/HELP texts must reach the ladder
    ("mock", "hc-dana", False, False),    # no keys: nothing to connect with
    ("mock", "", True, False),
    ("stable", "", True, False),
])
def test_photon2_inbound_wanted(monkeypatch, mode, users, keys, want):
    from app.main import photon2_inbound_wanted
    monkeypatch.setenv("PHOTON_MODE", mode)
    monkeypatch.setenv("HITIDE_LIVE_USERS", users)
    for k in ("PHOTON2_API_KEY", "PHOTON2_PROJECT_ID"):
        if keys:
            monkeypatch.setenv(k, "x")
        else:
            monkeypatch.delenv(k, raising=False)
    assert photon2_inbound_wanted() is want
