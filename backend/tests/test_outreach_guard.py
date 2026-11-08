"""Outreach service: moving-driver guard, allowlist, log, payload shape."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from api.schemas import OutreachEvent
from outreach import make_outreach
from outreach.allowlist import resolve_phone
from outreach.base import OutboundMessage

SECRET_PHONE = "+18305550142"


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def __call__(self, kind: str, payload: dict) -> None:
        self.events.append((kind, payload))


class Calls:
    """httpx transport that records requests and answers with a fixed status."""

    def __init__(self, status: int = 200) -> None:
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)
        self._status = status

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self._status, json={"ok": True, "success": True})


def _msg(**kw) -> OutboundMessage:
    base = dict(driver_id="d1", recipient="driver", channel="text",
                body="Flooded road ahead", phone="env:DEMO_PHONE_A", case_id="c1")
    return OutboundMessage(**{**base, **kw})


def _build(tmp_path: Path, moving: bool, calls: Calls | None = None):
    rec = Recorder()
    log = tmp_path / "outreach_log.jsonl"
    svc = make_outreach(rec, lambda _d: moving, log_path=log,
                        transport=(calls or Calls()).transport)
    return svc, rec, log


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("PHOTON_MODE", "DEMO_PHONE_A", "ELEVENLABS_API_KEY",
              "ELEVENLABS_AGENT_ID", "ELEVENLABS_PHONE_NUMBER_ID"):
        monkeypatch.delenv(k, raising=False)


# ---- moving-driver guard -------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["text", "poll", "voice"])
async def test_moving_driver_blocked_for_text_poll_voice(tmp_path, monkeypatch, channel):
    monkeypatch.setenv("PHOTON_MODE", "photon")
    monkeypatch.setenv("DEMO_PHONE_A", SECRET_PHONE)
    calls = Calls()
    svc, rec, log = _build(tmp_path, moving=True, calls=calls)
    out = await svc.send(_msg(channel=channel, poll_options=("a", "b")))
    assert out["status"] == "blocked"
    assert calls.requests == []  # nothing reached the network
    assert len(rec.events) == 1 and rec.events[0][0] == "outreach"
    assert rec.events[0][1]["status"] == "blocked"
    lines = log.read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["status"] == "blocked"


@pytest.mark.asyncio
async def test_moving_driver_tts_in_app_allowed(tmp_path):
    svc, rec, _ = _build(tmp_path, moving=True)
    out = await svc.send(_msg(channel="tts_in_app"))
    assert out["status"] == "sent" and out["mode"] == "mock"
    assert rec.events[0][1]["channel"] == "tts_in_app"


@pytest.mark.asyncio
@pytest.mark.parametrize("recipient", ["parent", "emergency_contact"])
@pytest.mark.parametrize("channel", ["text", "poll", "voice"])
async def test_parent_and_emergency_pass_guard_when_moving(tmp_path, recipient, channel):
    svc, _, _ = _build(tmp_path, moving=True)
    out = await svc.send(_msg(recipient=recipient, channel=channel))
    assert out["status"] == "sent"


@pytest.mark.asyncio
async def test_stationary_driver_not_blocked(tmp_path):
    svc, _, _ = _build(tmp_path, moving=False)
    assert (await svc.send(_msg()))["status"] == "sent"


@pytest.mark.asyncio
async def test_guard_receives_driver_id(tmp_path):
    seen: list[str] = []
    svc = make_outreach(Recorder(), lambda d: seen.append(d) or False,
                        log_path=tmp_path / "l.jsonl")
    await svc.send(_msg(driver_id="drv-9"))
    assert seen == ["drv-9"]


# ---- allowlist -----------------------------------------------------------

def test_resolve_env_phone(monkeypatch):
    monkeypatch.setenv("DEMO_PHONE_A", SECRET_PHONE)
    assert resolve_phone("env:DEMO_PHONE_A") == SECRET_PHONE


def test_resolve_env_unset_or_empty(monkeypatch):
    assert resolve_phone("env:DEMO_PHONE_A") is None
    monkeypatch.setenv("DEMO_PHONE_A", "")
    assert resolve_phone("env:DEMO_PHONE_A") is None
    monkeypatch.setenv("DEMO_PHONE_A", "   ")
    assert resolve_phone("env:DEMO_PHONE_A") is None


@pytest.mark.parametrize("raw", ["+18305550142", "", "8305550142", "env:", "env:HOME"])
def test_resolve_non_allowlisted_is_none(raw):
    assert resolve_phone(raw) is None


@pytest.mark.asyncio
async def test_real_number_never_sent_even_in_photon_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon")
    calls = Calls()
    svc, _, _ = _build(tmp_path, moving=False, calls=calls)
    out = await svc.send(_msg(phone="+18305550142"))
    assert out["mode"] == "mock" and out["status"] == "sent"
    assert calls.requests == []


@pytest.mark.asyncio
async def test_mock_mode_default_for_env_phone(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_PHONE_A", SECRET_PHONE)
    calls = Calls()
    svc, _, _ = _build(tmp_path, moving=False, calls=calls)
    out = await svc.send(_msg())
    assert out["mode"] == "mock" and calls.requests == []


# ---- photon dispatch -----------------------------------------------------

@pytest.mark.asyncio
async def test_photon_text_sent(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon")
    monkeypatch.setenv("DEMO_PHONE_A", SECRET_PHONE)
    calls = Calls()
    svc, _, _ = _build(tmp_path, moving=False, calls=calls)
    out = await svc.send(_msg())
    assert out["mode"] == "photon" and out["status"] == "sent"
    assert calls.requests[0].url.path == "/send"
    assert json.loads(calls.requests[0].content) == {"to": SECRET_PHONE, "body": "Flooded road ahead"}


@pytest.mark.asyncio
async def test_photon_poll_sent(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon")
    monkeypatch.setenv("DEMO_PHONE_A", SECRET_PHONE)
    calls = Calls()
    svc, _, _ = _build(tmp_path, moving=False, calls=calls)
    out = await svc.send(_msg(channel="poll", poll_options=("Safe", "Help")))
    assert out["status"] == "sent"
    assert json.loads(calls.requests[0].content)["options"] == ["Safe", "Help"]


@pytest.mark.asyncio
async def test_photon_failure_reports_failed_without_raising(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon")
    monkeypatch.setenv("DEMO_PHONE_A", SECRET_PHONE)
    svc, rec, log = _build(tmp_path, moving=False, calls=Calls(status=500))
    out = await svc.send(_msg())
    assert out["status"] == "failed" and out["mode"] == "photon"
    assert json.loads(log.read_text())["status"] == "failed"
    assert rec.events[0][1]["status"] == "failed"


@pytest.mark.asyncio
async def test_voice_without_env_falls_back_to_poll(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon")
    monkeypatch.setenv("DEMO_PHONE_A", SECRET_PHONE)
    calls = Calls()
    svc, _, _ = _build(tmp_path, moving=False, calls=calls)
    out = await svc.send(_msg(recipient="parent", channel="voice", body="Mia may be in danger"))
    assert out["status"] == "sent" and out["channel"] == "poll"
    assert "Are you okay?" in out["body"] and "voice unavailable" in out["body"].lower()
    req = calls.requests[0]
    assert req.url.path == "/poll"
    assert json.loads(req.content)["options"] == ["I'm safe", "I need help"]


@pytest.mark.asyncio
async def test_voice_with_env_places_call(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon")
    monkeypatch.setenv("DEMO_PHONE_A", SECRET_PHONE)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "ag")
    monkeypatch.setenv("ELEVENLABS_PHONE_NUMBER_ID", "pn")
    calls = Calls()
    svc, _, _ = _build(tmp_path, moving=False, calls=calls)
    out = await svc.send(_msg(recipient="parent", channel="voice"))
    assert out["status"] == "sent" and out["channel"] == "voice"
    assert calls.requests[0].url.host == "api.elevenlabs.io"


# ---- log + payload -------------------------------------------------------

@pytest.mark.asyncio
async def test_payload_matches_schema_and_log_has_no_phone(tmp_path, monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon")
    monkeypatch.setenv("DEMO_PHONE_A", SECRET_PHONE)
    svc, rec, log = _build(tmp_path, moving=False)
    out = await svc.send(_msg())
    OutreachEvent(**out)  # frozen contract
    required = {"id", "ts", "driver_id", "recipient", "channel", "body", "mode", "status", "case_id"}
    optional = {"provider", "call_id"}  # additive contract fields (docs/api-contract.md)
    assert required <= set(out) <= required | optional
    assert rec.events[0][1] == out
    raw_log = log.read_text()
    assert SECRET_PHONE not in raw_log and "DEMO_PHONE_A" not in raw_log
    assert SECRET_PHONE not in json.dumps(out)


@pytest.mark.asyncio
async def test_log_appends_one_line_per_attempt(tmp_path):
    svc, _, log = _build(tmp_path, moving=False)
    for _ in range(3):
        await svc.send(_msg())
    lines = log.read_text().splitlines()
    assert len(lines) == 3 and len({json.loads(x)["id"] for x in lines}) == 3


@pytest.mark.asyncio
async def test_emit_failure_does_not_raise(tmp_path):
    async def bad_emit(_k: str, _p: dict) -> None:
        raise RuntimeError("ws down")
    svc = make_outreach(bad_emit, lambda _d: False, log_path=tmp_path / "l.jsonl")
    assert (await svc.send(_msg()))["status"] == "sent"


@pytest.mark.asyncio
async def test_log_write_failure_does_not_raise(tmp_path):
    svc = make_outreach(Recorder(), lambda _d: False, log_path=tmp_path / "nodir" / "x" / "l.jsonl")
    assert (await svc.send(_msg()))["status"] == "sent"
