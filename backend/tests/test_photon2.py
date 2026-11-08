"""Photon 2.0 adapter via httpx MockTransport."""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from outreach import photon2

USER = "pho_usr_" + "1" * 25
AGENT = "pho_usr_" + "a" * 25
SPACE = "pho_spc_" + "2" * 25
HANDLE = "+18305550123"


class Api:
    def __init__(self, fail_path: str | None = None, status: int = 500, exc: Exception | None = None):
        self.requests: list[httpx.Request] = []
        self.fail_path, self.status, self.exc = fail_path, status, exc
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.exc:
            raise self.exc
        if self.fail_path and request.url.path.endswith(self.fail_path):
            return httpx.Response(self.status, json={"code": "X"})
        if request.url.path.endswith("/users"):
            return httpx.Response(201, json={"id": USER})
        if request.url.path.endswith("/spaces"):
            return httpx.Response(201, json={"id": SPACE})
        return httpx.Response(201, json={"id": "pho_msg_" + "3" * 25})

    def bodies(self, suffix: str) -> list[dict]:
        return [json.loads(r.content) for r in self.requests if r.url.path.endswith(suffix)]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    photon2.reset_cache()
    monkeypatch.setenv("PHOTON2_API_KEY", "sk-secret-key")
    monkeypatch.setenv("PHOTON2_PROJECT_ID", "proj1")
    monkeypatch.setenv("PHOTON2_AGENT_USER_ID", AGENT)
    yield
    photon2.reset_cache()


@pytest.mark.asyncio
async def test_send_text_happy_path_requests():
    api = Api()
    assert await photon2.send_text(HANDLE, "hello", transport=api.transport) == "sent"
    paths = [r.url.path for r in api.requests]
    assert paths == ["/v1/projects/proj1/users", "/v1/projects/proj1/spaces", "/v1/projects/proj1/messages"]
    assert all(r.url.host == "api.photon.codes" for r in api.requests)
    assert all(r.headers["authorization"] == "Bearer sk-secret-key" for r in api.requests)
    assert api.bodies("/users") == [{"handle": HANDLE, "platform": "imessage"}]
    assert api.bodies("/spaces") == [{"participantIds": [AGENT, USER], "platform": "imessage"}]
    assert api.bodies("/messages") == [
        {"spaceId": SPACE, "senderId": AGENT, "content": {"type": "text", "format": "plain", "text": "hello"}}
    ]


@pytest.mark.asyncio
async def test_send_poll_body():
    api = Api()
    assert await photon2.send_poll(HANDLE, "Are you okay?", ["I'm safe", "I need help"], transport=api.transport) == "sent"
    assert api.bodies("/messages")[0]["content"] == {
        "type": "poll",
        "question": "Are you okay?",
        "selectionMode": "single",
        "options": [{"id": "safe", "text": "I'm safe"}, {"id": "need_help", "text": "I need help"}],
    }


@pytest.mark.asyncio
async def test_idempotency_headers():
    api = Api()
    await photon2.send_text(HANDLE, "a", transport=api.transport)
    await photon2.send_text(HANDLE, "b", transport=api.transport)
    spaces = [r for r in api.requests if r.url.path.endswith("/spaces")]
    msgs = [r for r in api.requests if r.url.path.endswith("/messages")]
    assert spaces[0].headers["idempotency-key"] == f"spc-{USER}"
    assert all(r.headers.get("idempotency-key") for r in api.requests)
    keys = {m.headers["idempotency-key"] for m in msgs}
    assert len(keys) == 2


@pytest.mark.asyncio
async def test_cache_reuses_user_and_space():
    api = Api()
    await photon2.send_text(HANDLE, "a", transport=api.transport)
    await photon2.send_text(HANDLE, "b", transport=api.transport)
    paths = [r.url.path.rsplit("/", 1)[-1] for r in api.requests]
    assert paths == ["users", "spaces", "messages", "messages"]


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", ["/users", "/spaces", "/messages"])
async def test_4xx_at_each_step_fails(fail):
    api = Api(fail_path=fail, status=422)
    assert await photon2.send_text(HANDLE, "x", transport=api.transport) == "failed"


@pytest.mark.asyncio
async def test_failed_step_is_not_cached():
    api = Api(fail_path="/spaces", status=500)
    assert await photon2.send_text(HANDLE, "x", transport=api.transport) == "failed"
    ok = Api()
    assert await photon2.send_text(HANDLE, "x", transport=ok.transport) == "sent"
    # user was cached by the first attempt; the failed space step is retried
    assert [r.url.path.rsplit("/", 1)[-1] for r in ok.requests] == ["spaces", "messages"]


@pytest.mark.asyncio
async def test_timeout_and_network_error_fail_without_raising():
    assert await photon2.send_text(HANDLE, "x", transport=Api(exc=httpx.ReadTimeout("t")).transport) == "failed"
    assert await photon2.send_poll(HANDLE, "q", ["a"], transport=Api(exc=httpx.ConnectError("c")).transport) == "failed"


@pytest.mark.asyncio
async def test_malformed_response_fails():
    t = httpx.MockTransport(lambda r: httpx.Response(200, text="not json"))
    assert await photon2.send_text(HANDLE, "x", transport=t) == "failed"
    t2 = httpx.MockTransport(lambda r: httpx.Response(200, json={"nope": 1}))
    assert await photon2.send_text(HANDLE, "x", transport=t2) == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["PHOTON2_API_KEY", "PHOTON2_PROJECT_ID", "PHOTON2_AGENT_USER_ID"])
async def test_missing_env_fails_without_requests(monkeypatch, missing):
    monkeypatch.delenv(missing)
    api = Api()
    assert await photon2.send_text(HANDLE, "x", transport=api.transport) == "failed"
    assert api.requests == []


@pytest.mark.asyncio
async def test_logs_mask_phone_and_hide_key(caplog):
    caplog.set_level(logging.DEBUG)
    await photon2.send_text(HANDLE, "x", transport=Api(fail_path="/users", status=400).transport)
    assert caplog.text
    assert HANDLE not in caplog.text and "sk-secret-key" not in caplog.text


def test_mask_handle():
    assert photon2.mask_handle("+18305550123") == "+1******0123"
    assert photon2.mask_handle("ab") == "**"


OTHER_AGENT = "pho_usr_" + "b" * 25


@pytest.mark.asyncio
async def test_each_recipient_uses_its_own_shared_line_agent(monkeypatch):
    """Shared lines assign each recipient a different line, so each has a different agent sender."""
    monkeypatch.setenv("PHOTON2_AGENT_MAP", f"{HANDLE}={OTHER_AGENT},+18305550999={AGENT}")
    api = Api()
    assert await photon2.send_text(HANDLE, "hi", transport=api.transport) == "sent"
    assert api.bodies("/spaces") == [{"participantIds": [OTHER_AGENT, USER], "platform": "imessage"}]
    assert api.bodies("/messages")[0]["senderId"] == OTHER_AGENT


def test_agent_map_parsing_ignores_junk(monkeypatch):
    monkeypatch.setenv("PHOTON2_AGENT_MAP", f" {HANDLE}={OTHER_AGENT} , garbage, =x ,+1999= ")
    assert photon2.agent_map() == {HANDLE: OTHER_AGENT}
