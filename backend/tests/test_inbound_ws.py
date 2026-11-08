"""parse_ws_event on Photon 2.0 delivery payloads.

Shapes come from https://api.photon.codes/openapi.json (ImessageMessageReceivedEvent, TextContent,
PollVoteContent, PollOption, ImessageUserSnapshot) and the delivery(event, {seq, replyExpected}) frame in
https://photon.codes/docs/beta/websocket/events.
"""

import pytest

from outreach.photon2_ws import Photon2Inbound, parse_ws_event

SENDER = "+15550000001"


def _event(content: dict, status: str = "received", etype: str = "message.received", handle: str = SENDER) -> dict:
    return {
        "id": "evt_1",
        "type": etype,
        "apiVersion": "2026-07-01",
        "source": "imessage.photon",
        "timestamp": "2026-11-07T20:00:00Z",
        "data": {
            "projectId": "prj_1",
            "object": {
                "id": "msg_1",
                "platform": "imessage",
                "status": status,
                "sentBy": {"id": "usr_1", "platform": "imessage", "handle": handle, "kind": "user"},
                "content": content,
            },
        },
    }


def test_text_message():
    ev = _event({"type": "text", "format": "plain", "text": "I'm safe"})
    assert parse_ws_event(ev) == (SENDER, "I'm safe")


def test_poll_vote_safe_uses_option_id():
    ev = _event({"type": "poll.vote", "selectedOptions": [{"id": "safe", "text": "I'm safe"}]})
    assert parse_ws_event(ev) == (SENDER, "safe")


def test_poll_vote_need_help_maps_to_help():
    ev = _event({"type": "poll.vote", "selectedOptions": [{"id": "need_help", "text": "Need help"}]})
    assert parse_ws_event(ev) == (SENDER, "help")


def test_poll_vote_opaque_id_falls_back_to_option_text():
    ev = _event({"type": "poll.vote", "selectedOptions": [{"id": "opt_2", "text": "I need help"}]})
    assert parse_ws_event(ev) == (SENDER, "I need help")


def test_poll_vote_with_nothing_selected_is_none():
    assert parse_ws_event(_event({"type": "poll.vote", "selectedOptions": []})) is None


@pytest.mark.parametrize("status", ["dispatched", "accepted", "delivered", "failed"])
def test_our_outbound_messages_are_ignored(status):
    ev = _event({"type": "text", "format": "plain", "text": "Turn around"}, status=status)
    assert parse_ws_event(ev) is None


@pytest.mark.parametrize("etype", ["message.read", "message.delivered", "space.typing.update"])
def test_unrelated_event_types_are_ignored(etype):
    assert parse_ws_event(_event({"type": "text", "format": "plain", "text": "x"}, etype=etype)) is None


def test_non_text_content_is_ignored():
    assert parse_ws_event(_event({"type": "attachment"})) is None


@pytest.mark.parametrize("bad", [None, {}, [], "x", {"type": "message.received"},
                                 {"type": "message.received", "data": {"object": "x"}}])
def test_malformed_events_never_raise(bad):
    assert parse_ws_event(bad) is None  # type: ignore[arg-type]


def test_missing_or_blank_handle_is_ignored():
    ev = _event({"type": "text", "format": "plain", "text": "safe"}, handle="")
    assert parse_ws_event(ev) is None


@pytest.mark.asyncio
async def test_start_is_noop_outside_photon2_mode(monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "mock")
    monkeypatch.setenv("PHOTON2_API_KEY", "k")
    client = Photon2Inbound()

    async def cb(sender: str, text: str) -> None: ...

    await client.start(cb)
    assert client.running is False
    await client.stop()


@pytest.mark.asyncio
async def test_start_is_noop_without_api_key(monkeypatch):
    monkeypatch.setenv("PHOTON_MODE", "photon2")
    monkeypatch.delenv("PHOTON2_API_KEY", raising=False)
    client = Photon2Inbound()

    async def cb(sender: str, text: str) -> None: ...

    await client.start(cb)
    assert client.running is False
