"""handle_inbound: apply a reply from a phone to the right open case (fake runtime, no network)."""

from types import SimpleNamespace

import pytest

from outreach.inbound import handle_inbound

DRIVER_PHONE = "+15550000001"
CONTACT_PHONE = "+15550000002"


def _driver(did: str, phone: str = "env:DEMO_PHONE_A", contact: str = "env:DEMO_PHONE_B"):
    return SimpleNamespace(id=did, phone=phone, emergency_contact=SimpleNamespace(phone=contact))


class FakeRunner:
    def __init__(self, cases: dict, opened: dict):
        self.world = SimpleNamespace(cases=cases, case_opened_s=opened)
        self.replies: list[tuple] = []

    async def reply(self, case_id, kind, by="driver"):
        self.replies.append((case_id, kind, by))


def _rt(drivers, cases, opened):
    return SimpleNamespace(drivers=drivers, runner=FakeRunner(cases, opened))


def _case(cid: str, did: str, state: str = "open"):
    return SimpleNamespace(id=cid, driver_id=did, state=state)


@pytest.fixture(autouse=True)
def _phones(monkeypatch):
    monkeypatch.setenv("DEMO_PHONE_A", DRIVER_PHONE)
    monkeypatch.setenv("DEMO_PHONE_B", CONTACT_PHONE)


@pytest.mark.asyncio
async def test_unparseable_text_is_not_matched():
    rt = _rt([_driver("d1")], {"c1": _case("c1", "d1")}, {"c1": 1.0})
    assert await handle_inbound(rt, DRIVER_PHONE, "what time is it") == {"ok": True, "matched": False}
    assert rt.runner.replies == []


@pytest.mark.asyncio
async def test_driver_reply_applies_to_their_case():
    rt = _rt([_driver("d1")], {"c1": _case("c1", "d1")}, {"c1": 1.0})
    out = await handle_inbound(rt, DRIVER_PHONE, "I'm safe")
    assert out == {"ok": True, "matched": True, "case_id": "c1", "reply": "safe"}
    assert rt.runner.replies == [("c1", "safe", "driver")]


@pytest.mark.asyncio
async def test_emergency_contact_reply_is_tagged():
    rt = _rt([_driver("d1")], {"c1": _case("c1", "d1")}, {"c1": 1.0})
    out = await handle_inbound(rt, CONTACT_PHONE, "help")
    assert out["reply"] == "need_help"
    assert rt.runner.replies == [("c1", "need_help", "emergency_contact")]


@pytest.mark.asyncio
async def test_resolved_cases_are_ignored():
    rt = _rt([_driver("d1")], {"c1": _case("c1", "d1", "resolved")}, {"c1": 1.0})
    assert (await handle_inbound(rt, DRIVER_PHONE, "safe"))["matched"] is False
    assert rt.runner.replies == []


@pytest.mark.asyncio
async def test_unknown_sender_is_ignored():
    rt = _rt([_driver("d1")], {"c1": _case("c1", "d1")}, {"c1": 1.0})
    assert (await handle_inbound(rt, "+19998887777", "safe"))["matched"] is False
    assert rt.runner.replies == []


@pytest.mark.asyncio
async def test_unresolvable_phone_ref_never_matches():
    rt = _rt([_driver("d1", phone="+15550000001", contact="env:DEMO_PHONE_MISSING")],
             {"c1": _case("c1", "d1")}, {"c1": 1.0})
    assert (await handle_inbound(rt, DRIVER_PHONE, "safe"))["matched"] is False


@pytest.mark.asyncio
async def test_most_recently_opened_case_wins():
    rt = _rt([_driver("d1"), _driver("d2")],
             {"c1": _case("c1", "d1"), "c2": _case("c2", "d2")}, {"c1": 5.0, "c2": 9.0})
    out = await handle_inbound(rt, DRIVER_PHONE, "safe")
    assert out["case_id"] == "c2"


@pytest.mark.asyncio
async def test_case_without_driver_is_skipped():
    rt = _rt([_driver("d1")], {"c9": _case("c9", "ghost")}, {"c9": 1.0})
    assert (await handle_inbound(rt, DRIVER_PHONE, "safe"))["matched"] is False
