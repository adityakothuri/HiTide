"""Photon sidecar adapter and ElevenLabs voice adapter, via httpx MockTransport."""

from __future__ import annotations

import json

import httpx
import pytest

from outreach import photon_spectrum, voice_elevenlabs


def _transport(status: int = 200, exc: Exception | None = None):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if exc:
            raise exc
        return httpx.Response(status, json={"success": True})

    return httpx.MockTransport(handler), seen


@pytest.mark.asyncio
async def test_send_text_posts_contract():
    t, seen = _transport()
    assert await photon_spectrum.send_text("+1830", "hi", transport=t) == "sent"
    assert seen[0].method == "POST" and str(seen[0].url) == "http://localhost:8787/send"
    assert json.loads(seen[0].content) == {"to": "+1830", "body": "hi"}


@pytest.mark.asyncio
async def test_send_poll_posts_contract():
    t, seen = _transport()
    assert await photon_spectrum.send_poll("+1830", "OK?", ("a", "b"), transport=t) == "sent"
    assert str(seen[0].url) == "http://localhost:8787/poll"
    assert json.loads(seen[0].content) == {"to": "+1830", "question": "OK?", "options": ["a", "b"]}


@pytest.mark.asyncio
async def test_sidecar_url_override(monkeypatch):
    monkeypatch.setenv("SPECTRUM_SIDECAR_URL", "http://sidecar:9000")
    t, seen = _transport()
    await photon_spectrum.send_text("+1", "x", transport=t)
    assert seen[0].url.host == "sidecar" and seen[0].url.port == 9000


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 500, 503])
async def test_http_errors_become_failed(status):
    t, _ = _transport(status)
    assert await photon_spectrum.send_text("+1", "x", transport=t) == "failed"
    assert await photon_spectrum.send_poll("+1", "q", ("a",), transport=t) == "failed"


@pytest.mark.asyncio
async def test_network_errors_become_failed_and_never_log_phone(caplog):
    t, _ = _transport(exc=httpx.ConnectError("refused"))
    with caplog.at_level("DEBUG"):
        assert await photon_spectrum.send_text("+18305550142", "x", transport=t) == "failed"
    assert "+18305550142" not in caplog.text and caplog.records


@pytest.mark.asyncio
async def test_timeout_becomes_failed():
    t, _ = _transport(exc=httpx.ReadTimeout("slow"))
    assert await photon_spectrum.send_text("+1", "x", transport=t) == "failed"


def test_timeout_is_ten_seconds():
    assert photon_spectrum.TIMEOUT_S == 10.0 and voice_elevenlabs.TIMEOUT_S == 10.0


@pytest.fixture
def el_env(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "key123")
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "agent_1")
    monkeypatch.setenv("ELEVENLABS_PHONE_NUMBER_ID", "phnum_1")


@pytest.mark.asyncio
async def test_place_call_request_shape(el_env):
    t, seen = _transport()
    assert await voice_elevenlabs.place_call("+1830", "Hello, are you okay?", transport=t) == "sent"
    r = seen[0]
    assert str(r.url) == "https://api.elevenlabs.io/v1/convai/sip-trunk/outbound-call"
    assert r.headers["xi-api-key"] == "key123"
    body = json.loads(r.content)
    assert body["agent_id"] == "agent_1"
    assert body["agent_phone_number_id"] == "phnum_1"
    assert body["to_number"] == "+1830"
    first = body["conversation_initiation_client_data"]["conversation_config_override"]["agent"]["first_message"]
    assert first == "Hello, are you okay?"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 422, 500])
async def test_place_call_errors_failed(el_env, status):
    t, _ = _transport(status)
    assert await voice_elevenlabs.place_call("+1", "hi", transport=t) == "failed"


@pytest.mark.asyncio
async def test_place_call_network_error_failed(el_env):
    t, _ = _transport(exc=httpx.ConnectError("x"))
    assert await voice_elevenlabs.place_call("+1", "hi", transport=t) == "failed"


@pytest.mark.asyncio
async def test_place_call_success_false_in_body_is_failed(el_env):
    t = httpx.MockTransport(lambda r: httpx.Response(200, json={"success": False, "message": "no"}))
    assert await voice_elevenlabs.place_call("+1", "hi", transport=t) == "failed"


def test_voice_configured(monkeypatch, el_env):
    assert voice_elevenlabs.voice_configured() is True
    monkeypatch.delenv("ELEVENLABS_AGENT_ID")
    assert voice_elevenlabs.voice_configured() is False
