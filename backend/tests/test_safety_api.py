"""Per-user danger API: validation, origin guard, enroll (no phone in responses), ping -> assessment -> outreach."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from sim.region_flood import epoch

pytest.importorskip("osmnx")
UNTRUSTED = {"origin": "https://evil.invalid"}


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("safety")
    mp = pytest.MonkeyPatch()
    mp.setenv("PHOTON_MODE", "mock")
    mp.setenv("EVIDENCE_POLL_SECONDS", "0")
    mp.setenv("HITIDE_DB_BACKEND", "sqlite")
    mp.setenv("SAFETY_REGISTRY_PATH", str(tmp / "registry.json"))
    mp.setenv("SAFETY_STATE_PATH", str(tmp / "state.json"))
    from app.main import app

    with TestClient(app) as c:
        c.tmp = tmp  # type: ignore[attr-defined]
        yield c
    mp.undo()


def _hill(client):
    from app.hill_runtime import get_hill
    return client.portal.call(get_hill, client.app)


def _step(client, hhmm):
    """Advance the replay loop to a time and run the safety monitor once (what the replay does every tick)."""
    h = _hill(client)
    h.loop.step(epoch(f"2025-07-04T{hhmm}:00-05:00"))
    client.portal.call(h.safety.after_step, h.loop)
    return h


def test_location_before_any_flood_picture_is_409(client):
    _hill(client).safety.reset("replay")
    r = client.post("/api/users/hc-ruth/location", json={"lat": 30.06, "lon": -99.33})
    assert r.status_code == 409


@pytest.mark.parametrize("body", [
    {"lat": 91, "lon": 0}, {"lat": 30, "lon": -181}, {"lat": 30, "lon": -99, "speed_mps": -1},
    {"lat": 30, "lon": -99, "heading_deg": 360}, {"lat": 30, "lon": -99, "extra": 1}, {"lon": -99}])
def test_bad_location_is_422(client, body):
    assert client.post("/api/users/hc-ruth/location", json=body).status_code == 422


def test_unknown_user_404_and_untrusted_origin_403(client):
    assert client.get("/api/users/nobody/danger").status_code == 404
    assert client.post("/api/users/hc-ruth/location", json={"lat": 30.06, "lon": -99.33}, headers=UNTRUSTED).status_code == 403
    assert client.post("/api/users/hc-ruth/reply", json={"reply": "safe"}, headers=UNTRUSTED).status_code == 403


def test_enroll_validates_and_never_echoes_phone(client):
    base = {"id": "real-user-1", "name": "Pat Doe", "phone": "+18305550123", "home_lat": 30.05, "home_lon": -99.14,
            "vehicle_type": "suv", "needs": ["hearing_loss"], "consent_flood_alerts": True}
    assert client.post("/api/users", json={**base, "consent_flood_alerts": False}).status_code == 422
    assert client.post("/api/users", json={**base, "phone": "830-555-0123"}).status_code == 422
    assert client.post("/api/users", json={**base, "needs": ["superpowers"]}).status_code == 422
    assert client.post("/api/users", json={**base, "id": "hc-ruth"}).status_code == 409
    r = client.post("/api/users", json=base)
    assert r.status_code == 201 and "phone" not in r.text and "0123" not in r.text
    assert (client.tmp / "registry.json").exists()  # type: ignore[attr-defined]
    listing = client.get("/api/users?limit=2000").json()
    assert any(u["id"] == "real-user-1" for u in listing["users"]) and "+1830" not in str(listing)


def test_replay_ping_assessment_and_ladder(client):
    _step(client, "01:00")
    _step(client, "04:15")
    r = client.post("/api/users/hc-ruth/location", json={"lat": 30.0688, "lon": -99.3345})
    assert r.status_code == 200
    body = r.json()
    assert body["level"] in ("danger", "critical") and body["reasons"]
    assert body["vulnerability"]["needs_priority"] is True and "phone" not in str(body)
    assert body["response"]["episode_level"] in ("danger", "critical")
    d = client.get("/api/users/hc-ruth/danger").json()
    assert d["level"] == body["level"] and d["hazard"]["coverage"] == "region"
    risk = client.get("/api/users/at-risk?min_level=danger").json()
    assert risk["total"] >= 1 and risk["users"][0]["level"] in ("danger", "critical")
    assert client.get("/api/users/at-risk?min_level=panic").status_code == 422
    s = client.get("/api/safety/summary").json()
    assert s["ready"] and s["users"] >= 250 and sum(s["levels"].values()) >= 250


def test_reply_safe_then_route(client):
    r = client.post("/api/users/hc-ruth/reply", json={"reply": "safe"})
    assert r.status_code == 200 and r.json()["response"]["safe_until"] is not None
    pts = [[30.0688, -99.3345], [30.0705, -99.3330], [30.0720, -99.3300]]
    r = client.post("/api/users/hc-ruth/route", json={"points": pts})
    assert r.status_code == 200 and r.json()["edges_matched"] >= 1
    assert client.post("/api/users/hc-ruth/route", json={"points": [[30, -99]]}).status_code == 422


def test_outreach_events_are_mock_and_phone_free(client):
    from app.config import DATA_DIR
    h = _hill(client)
    assert h.safety is not None and client.app.state.runtime.safety is h.safety
    log = DATA_DIR / "outreach_log.jsonl"
    if log.exists():
        tail = log.read_text().splitlines()[-50:]
        assert not any("+1830" in line for line in tail)
    asyncio.run(asyncio.sleep(0))


def test_enroll_cannot_overwrite_or_inject_links(client):
    base = {"id": "real-user-2", "name": "Sam Lee", "phone": "+18305550124", "home_lat": 30.05, "home_lon": -99.14,
            "consent_flood_alerts": True}
    assert client.post("/api/users", json={**base, "name": "http://evil.example/x"}).status_code == 422
    assert client.post("/api/users", json=base).status_code == 201
    assert client.post("/api/users", json={**base, "phone": "+18305550999"}).status_code == 409  # no takeover


def test_real_users_location_hidden_below_danger(client):
    r = client.post("/api/users/real-user-2/location", json={"lat": 30.1, "lon": -99.44})
    body = r.json()
    if body["level"] in ("danger", "critical"):
        pytest.skip("this spot is in danger in the current replay state")
    assert "lat" not in body["location"] and "lat" not in body["hazard"]
    assert client.get("/api/users/real-user-2/danger").json()["location"].get("lat") is None
    listing = {u["id"]: u for u in client.get("/api/users?limit=2000").json()["users"]}
    assert listing["real-user-2"]["name"] == "Sam" and listing["real-user-2"]["age"] is None


def test_api_key_guards_enroll_and_reply(client, monkeypatch):
    monkeypatch.setenv("SAFETY_API_KEY", "k3y")
    assert client.post("/api/users/hc-ruth/reply", json={"reply": "safe"}).status_code == 401
    ok = client.post("/api/users/hc-ruth/reply", json={"reply": "safe"}, headers={"x-safety-key": "k3y"})
    assert ok.status_code == 200


def test_messages_never_carry_a_user_supplied_link():
    from safety.messages import first_name
    assert first_name("http://evil.example/x Smith") == "there"
    assert first_name("José María") == "José"


def test_nan_ts_rejected(client):
    r = client.post("/api/users/hc-ruth/location", content='{"lat": 30.06, "lon": -99.33, "ts": NaN}',
                    headers={"content-type": "application/json"})
    assert r.status_code == 422


def test_api_key_guards_location_too(client, monkeypatch):
    monkeypatch.setenv("SAFETY_API_KEY", "k3y")
    assert client.post("/api/users/hc-ruth/location", json={"lat": 30.06, "lon": -99.33}).status_code == 401


def test_region_gauges_is_the_small_gauge_list_the_phone_polls(client):
    _step(client, "07:00")
    r = client.get("/api/region/gauges")
    assert r.status_code == 200
    gauges = r.json()
    assert any(g["site"] == "08166200" for g in gauges)
    assert all({"site", "name", "stage_ft", "observed_at", "rate_ft_per_hr"} <= g.keys() for g in gauges)


def test_phone_app_persona_is_enrolled_and_assessed(client):
    """hc-dana is the mobile app's user (mobile/): consented, sim-only phones, and assessed like everyone else."""
    _step(client, "07:00")
    r = client.get("/api/users/hc-dana/danger")
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == "hc-dana" and "response" in body
    assert "phone" not in str(body)


def test_flood_layer_window_has_flooded_roads_with_geometry_at_the_crest(client):
    _step(client, "07:20")
    r = client.get("/api/region/flood-layer", params={"bbox": "-99.17,30.00,-99.10,30.06"})
    assert r.status_code == 200
    body = r.json()
    assert body["segments"], "the July 4 crest floods roads in Kerrville"
    assert all(s["status"] != "open" and len(s["coords"]) >= 2 for s in body["segments"])
    assert body["points"] and all(p["status"] in ("open", "unknown", "likely_flooded", "confirmed_flooded") for p in body["points"])
    assert client.get("/api/region/flood-layer", params={"bbox": "-100,29,-97,32"}).status_code == 422


def test_directions_and_mock_assistant_line_for_the_app_user(client, monkeypatch):
    monkeypatch.delenv("HITIDE_ASSISTANT_LIVE", raising=False)
    _step(client, "07:20")
    client.post("/api/users/hc-dana/location", json={"lat": 30.03785, "lon": -99.13361, "speed_mps": 0})
    d = client.get("/api/users/hc-dana/directions")
    assert d.status_code == 200 and d.json()["text"] and d.json()["kind"] in ("route", "stay", "none")
    assert "safe route" not in d.json()["text"].lower()
    a = client.post("/api/users/hc-dana/assistant")
    assert a.status_code == 200 and a.json()["mode"] == "mock" and a.json()["phone"] is None
    assert any("assistant call requested" in e["what"] for e in a.json()["response"]["timeline"])
    assert client.post("/api/users/hc-dana/assistant", headers=UNTRUSTED).status_code == 403


def test_route_options_for_the_app_trip(client):
    _step(client, "07:20")
    home, work = "-99.1169,30.01281", "-99.14057,30.04748"
    r = client.get("/api/routes/options", params={"start": home, "end": work})
    assert r.status_code == 200
    opts = r.json()["options"]
    assert 1 <= len(opts) <= 3 and any(o["label"] == "Fastest" for o in opts)
    order = {"clear": 0, "likely": 1, "flooded": 2}
    assert [order[o["status"]] for o in opts] == sorted(order[o["status"]] for o in opts)   # least flooding on top
    assert all(o["status"] in ("flooded", "likely", "clear") and o["coords"] for o in opts)
    assert client.get("/api/routes/options", params={"start": "0,0", "end": work}).status_code == 422
    assert client.get("/api/routes/options", params={"start": "x", "end": work}).status_code == 422
