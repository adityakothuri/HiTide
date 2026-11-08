"""ElevenLabs voice adapter: CallResult, dynamic variables, conversation fetch."""

from __future__ import annotations

import json

import httpx
import pytest

from outreach import voice_elevenlabs
from outreach.voice_elevenlabs import CallResult


@pytest.fixture
def el_env(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "key123")
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "agent_1")
    monkeypatch.setenv("ELEVENLABS_PHONE_NUMBER_ID", "phnum_1")


def _t(payload=None, status=200, exc=None):
    seen: list[httpx.Request] = []

    def handler(r: httpx.Request) -> httpx.Response:
        seen.append(r)
        if exc:
            raise exc
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handler), seen


OK = {"success": True, "message": "ok", "conversation_id": "conv_9", "sip_call_id": "sip_1"}


@pytest.mark.asyncio
async def test_place_call_returns_conversation_id_and_sends_variables(el_env):
    t, seen = _t(OK)
    res = await voice_elevenlabs.place_call("+1830", "Hi", {"street": "Water St"}, transport=t)
    assert res == CallResult("sent", "conv_9")
    data = json.loads(seen[0].content)["conversation_initiation_client_data"]
    # first message travels as a dynamic variable: ElevenLabs rejects first_message overrides on SIP calls
    assert data["dynamic_variables"] == {"street": "Water St", "opening_line": "Hi"}
    assert "conversation_config_override" not in data


@pytest.mark.asyncio
async def test_place_call_without_variables_sends_only_opening_line(el_env):
    t, seen = _t(OK)
    await voice_elevenlabs.place_call("+1", "Hi", transport=t)
    assert json.loads(seen[0].content)["conversation_initiation_client_data"] == {"dynamic_variables": {"opening_line": "Hi"}}


@pytest.mark.asyncio
async def test_place_call_missing_conversation_id_still_sent(el_env):
    t, _ = _t({"success": True, "message": "ok"})
    assert await voice_elevenlabs.place_call("+1", "Hi", transport=t) == CallResult("sent", None)


@pytest.mark.asyncio
async def test_place_call_unconfigured_failed(monkeypatch):
    for n in ("ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID", "ELEVENLABS_PHONE_NUMBER_ID"):
        monkeypatch.delenv(n, raising=False)
    assert await voice_elevenlabs.place_call("+1", "Hi") == CallResult("failed", None)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 422, 500])
async def test_place_call_http_errors_failed(el_env, status):
    t, _ = _t({"detail": "x"}, status)
    assert await voice_elevenlabs.place_call("+1", "Hi", transport=t) == CallResult("failed", None)


@pytest.mark.asyncio
async def test_place_call_network_error_failed(el_env):
    t, _ = _t(exc=httpx.ConnectError("x"))
    assert await voice_elevenlabs.place_call("+1", "Hi", transport=t) == CallResult("failed", None)


@pytest.mark.asyncio
async def test_place_call_never_logs_phone(el_env, caplog):
    t, _ = _t(exc=httpx.ConnectError("x"))
    with caplog.at_level("DEBUG"):
        await voice_elevenlabs.place_call("+18305550142", "Hi", transport=t)
    assert "+18305550142" not in caplog.text and caplog.records


@pytest.mark.asyncio
async def test_get_conversation_request_and_payload(el_env):
    payload = {"status": "done", "transcript": []}
    t, seen = _t(payload)
    assert await voice_elevenlabs.get_conversation("conv_9", transport=t) == payload
    assert str(seen[0].url) == "https://api.elevenlabs.io/v1/convai/conversations/conv_9"
    assert seen[0].method == "GET" and seen[0].headers["xi-api-key"] == "key123"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["http", "net", "list", "nokey"])
async def test_get_conversation_failures_return_none(el_env, monkeypatch, kind):
    if kind == "http":
        t, _ = _t({"detail": "x"}, 404)
    elif kind == "net":
        t, _ = _t(exc=httpx.ReadTimeout("slow"))
    elif kind == "list":
        t, _ = _t([1, 2])
    else:
        monkeypatch.delenv("ELEVENLABS_API_KEY")
        t, _ = _t({})
    assert await voice_elevenlabs.get_conversation("conv_9", transport=t) is None
