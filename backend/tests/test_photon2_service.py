"""OutreachService dispatch by photon_mode(): stable / photon2 / mock, voice contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

import pytest

from api.schemas import OutreachEvent
from outreach import make_outreach, photon2, photon_spectrum, voice_elevenlabs
from outreach.base import OutboundMessage

PHONE = "+18305550142"
ENV_KEYS = (
    "PHOTON_MODE", "DEMO_PHONE_A", "SPECTRUM_PROJECT_ID", "SPECTRUM_PROJECT_SECRET",
    "ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID", "ELEVENLABS_PHONE_NUMBER_ID",
)


@dataclass(frozen=True)
class FakeCallResult:
    status: Literal["sent", "failed"]
    conversation_id: str | None


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def __call__(self, kind: str, payload: dict) -> None:
        self.events.append((kind, payload))


class Fakes:
    """Records calls and returns scripted statuses for each backend."""

    def __init__(self, monkeypatch, photon2_status="sent", stable_status="sent", call=None):
        self.calls: list[tuple] = []

        async def p2_text(handle, text, *, transport=None):
            self.calls.append(("p2_text", handle, text))
            return photon2_status

        async def p2_poll(handle, q, options, *, transport=None):
            self.calls.append(("p2_poll", handle, q, tuple(options)))
            return photon2_status

        async def st_text(to, body, *, transport=None):
            self.calls.append(("st_text", to, body))
            return stable_status

        async def st_poll(to, q, options, *, transport=None):
            self.calls.append(("st_poll", to, q, tuple(options)))
            return stable_status

        async def place_call(to, first_message, variables=None, *, transport=None):
            self.calls.append(("call", to, first_message, dict(variables or {})))
            return call or FakeCallResult("sent", "conv_123")

        monkeypatch.setattr(photon2, "send_text", p2_text)
        monkeypatch.setattr(photon2, "send_poll", p2_poll)
        monkeypatch.setattr(photon_spectrum, "send_text", st_text)
        monkeypatch.setattr(photon_spectrum, "send_poll", st_poll)
        monkeypatch.setattr(voice_elevenlabs, "place_call", place_call)

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DEMO_PHONE_A", PHONE)


def _msg(**kw) -> OutboundMessage:
    base = dict(driver_id="d1", recipient="driver", channel="text", body="Turn around",
                phone="env:DEMO_PHONE_A", case_id="c1")
    return OutboundMessage(**{**base, **kw})


def _svc(tmp_path: Path):
    rec = Recorder()
    return make_outreach(rec, lambda _d: False, log_path=tmp_path / "log.jsonl"), rec


def _voice_env(monkeypatch):
    for k in ("ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID", "ELEVENLABS_PHONE_NUMBER_ID"):
        monkeypatch.setenv(k, "x")


def _spectrum_env(monkeypatch):
    monkeypatch.setenv("SPECTRUM_PROJECT_ID", "p")
    monkeypatch.setenv("SPECTRUM_PROJECT_SECRET", "s")


# ---- OutboundMessage.variables -------------------------------------------

def test_variables_default_empty_and_hashable():
    m = _msg()
    assert dict(m.variables) == {}
    hash(m)
    assert dict(_msg(variables={"driver_name": "Mia"}).variables) == {"driver_name": "Mia"}
    hash(_msg(variables=MappingProxyType({"a": "b"})))


# ---- dispatch ------------------------------------------------------------

@pytest.mark.asyncio
async def test_photon2_text_uses_photon2_only(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon2")
    f = Fakes(monkeypatch)
    out = await _svc(tmp_path)[0].send(_msg())
    assert f.calls == [("p2_text", PHONE, "Turn around")]
    assert out["mode"] == "photon" and out["status"] == "sent" and out["provider"] == "photon2"
    OutreachEvent(**out)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["stable", "photon"])
async def test_stable_text_uses_spectrum(tmp_path, monkeypatch, mode):
    monkeypatch.setenv("PHOTON_MODE", mode)
    f = Fakes(monkeypatch)
    out = await _svc(tmp_path)[0].send(_msg())
    assert f.names() == ["st_text"]
    assert out["mode"] == "photon" and out["provider"] == "stable"


@pytest.mark.asyncio
async def test_photon2_poll_default_options(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon2")
    f = Fakes(monkeypatch)
    out = await _svc(tmp_path)[0].send(_msg(channel="poll", body="Are you okay?"))
    assert f.calls == [("p2_poll", PHONE, "Are you okay?", ("I'm safe", "I need help"))]
    assert out["channel"] == "poll" and out["provider"] == "photon2"


@pytest.mark.asyncio
async def test_mock_mode_sends_nothing(tmp_path, monkeypatch):
    f = Fakes(monkeypatch)
    out = await _svc(tmp_path)[0].send(_msg())
    assert f.calls == []
    assert out["mode"] == "mock" and out["status"] == "sent"
    assert "provider" not in out and "call_id" not in out
    OutreachEvent(**out)


@pytest.mark.asyncio
async def test_non_allowlisted_phone_stays_mock_in_photon2(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon2")
    f = Fakes(monkeypatch)
    out = await _svc(tmp_path)[0].send(_msg(phone="+15555550100"))
    assert f.calls == [] and out["mode"] == "mock"


# ---- photon2 -> stable fallback ------------------------------------------

@pytest.mark.asyncio
async def test_photon2_failure_retries_once_via_stable_with_creds(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon2")
    _spectrum_env(monkeypatch)
    f = Fakes(monkeypatch, photon2_status="failed")
    out = await _svc(tmp_path)[0].send(_msg())
    assert f.names() == ["p2_text", "st_text"]
    assert out["status"] == "sent" and out["provider"] == "stable"


@pytest.mark.asyncio
async def test_photon2_poll_failure_retries_via_stable(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon2")
    _spectrum_env(monkeypatch)
    f = Fakes(monkeypatch, photon2_status="failed")
    out = await _svc(tmp_path)[0].send(_msg(channel="poll", poll_options=("A", "B")))
    assert f.names() == ["p2_poll", "st_poll"] and f.calls[1][3] == ("A", "B")
    assert out["provider"] == "stable"


@pytest.mark.asyncio
async def test_photon2_failure_without_spectrum_creds_reports_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon2")
    f = Fakes(monkeypatch, photon2_status="failed")
    out = await _svc(tmp_path)[0].send(_msg())
    assert f.names() == ["p2_text"]
    assert out["status"] == "failed" and out["provider"] == "photon2"


@pytest.mark.asyncio
async def test_both_fail_reports_failed_once_each(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon2")
    _spectrum_env(monkeypatch)
    f = Fakes(monkeypatch, photon2_status="failed", stable_status="failed")
    out = await _svc(tmp_path)[0].send(_msg())
    assert f.names() == ["p2_text", "st_text"] and out["status"] == "failed"


# ---- voice ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_voice_passes_variables_and_reports_call_id(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon2")
    _voice_env(monkeypatch)
    f = Fakes(monkeypatch)
    msg = _msg(recipient="parent", channel="voice", variables={"driver_name": "Mia"})
    out = await _svc(tmp_path)[0].send(msg)
    assert f.calls == [("call", PHONE, "Turn around", {"driver_name": "Mia"})]
    assert out["channel"] == "voice" and out["status"] == "sent"
    assert out["call_id"] == "conv_123" and out["mode"] == "photon"
    OutreachEvent(**out)


@pytest.mark.asyncio
async def test_voice_failure_falls_back_to_poll(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon2")
    _voice_env(monkeypatch)
    f = Fakes(monkeypatch, call=FakeCallResult("failed", None))
    out = await _svc(tmp_path)[0].send(_msg(recipient="parent", channel="voice"))
    assert f.names() == ["call", "p2_poll"]
    assert out["channel"] == "poll" and out["status"] == "sent" and "call_id" not in out


@pytest.mark.asyncio
async def test_voice_without_env_falls_back_to_poll(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon2")
    f = Fakes(monkeypatch)
    out = await _svc(tmp_path)[0].send(_msg(recipient="parent", channel="voice"))
    assert f.names() == ["p2_poll"]
    assert out["channel"] == "poll" and "voice unavailable" in out["body"].lower()


@pytest.mark.asyncio
async def test_voice_exception_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon2")
    _voice_env(monkeypatch)
    Fakes(monkeypatch)

    async def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(voice_elevenlabs, "place_call", boom)
    out = await _svc(tmp_path)[0].send(_msg(recipient="parent", channel="voice"))
    assert out["channel"] == "poll"


@pytest.mark.asyncio
async def test_log_never_contains_phone(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon2")
    Fakes(monkeypatch)
    svc, _ = _svc(tmp_path)
    await svc.send(_msg())
    assert PHONE not in (tmp_path / "log.jsonl").read_text()
    assert json.loads((tmp_path / "log.jsonl").read_text())["provider"] == "photon2"
