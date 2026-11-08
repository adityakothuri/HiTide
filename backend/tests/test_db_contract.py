"""One contract, every backend: the in-memory store, the file fallback, and a real SpacetimeDB database.

The SpacetimeDB run publishes the module to a throwaway database on the local server and deletes it afterwards
(skipped when the `spacetime` CLI or server isn't available). Marker: -m spacetime.
"""

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import httpx
import pytest

from app.config import REPO_DIR
from db.evidence import SpacetimeEvidenceStore
from db.spacetime import SpacetimeClient, SpacetimeConfig, SpacetimeError
from db.store import FileDataStore, MemoryDataStore, SpacetimeDataStore
from evidence.store import Store

MODULE = REPO_DIR / "spacetime" / "floodwatch" / "spacetimedb"
CLI = shutil.which("spacetime") or str(Path.home() / ".local" / "bin" / "spacetime")


def _server_up() -> bool:
    try:
        return httpx.get("http://127.0.0.1:3000/v1/ping", timeout=1).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture(scope="module")
def spacetime_client():
    if os.environ.get("SKIP_SPACETIME") == "1" or not Path(CLI).exists() or not _server_up():
        pytest.skip("SpacetimeDB CLI/server not available")
    name = f"floodwatch-test-{uuid.uuid4().hex[:8]}"
    pub = subprocess.run([CLI, "publish", name, "--server", "local", "-p", str(MODULE), "--yes"],
                         capture_output=True, text=True, timeout=240, cwd=MODULE.parent)
    if pub.returncode != 0:
        pytest.skip(f"could not publish test module: {pub.stderr[-300:]}")
    client = SpacetimeClient(SpacetimeConfig("http://127.0.0.1:3000", name, SpacetimeConfig.from_env().token))
    yield client
    client.close()
    subprocess.run([CLI, "delete", name, "--server", "local", "--yes"], capture_output=True, timeout=60)


@pytest.fixture(params=["memory", "file", pytest.param("spacetime", marks=pytest.mark.spacetime)])
def data(request, tmp_path):
    if request.param == "memory":
        return MemoryDataStore()
    if request.param == "file":
        return FileDataStore(region_users=tmp_path / "none.json", registry=tmp_path / "reg.json", log_path=tmp_path / "log.jsonl")
    client = request.getfixturevalue("spacetime_client")
    store = SpacetimeDataStore(client)
    store.wipe_runtime("all_runtime")
    return store


def _user(uid, simulated=True, phone=None):
    return {"id": uid, "name": "Ruth Alvarez", "age": 78, "phone": phone or f"sim:{uid}", "home": {"lat": 30.0688, "lon": -99.3345},
            "contact_name": "Kim", "contact_phone": f"sim:{uid}-c", "parent_phone": None, "tags": ["demo"],
            "profile": {"consent": {"flood_alerts": True}, "needs": ["mobility_assist"]}, "simulated": simulated}


def test_users_seed_load_and_enroll_never_overwrites(data):
    uid = f"u-{uuid.uuid4().hex[:6]}"
    data.seed_users([_user(uid)])
    got = {u["id"]: u for u in data.load_users()}[uid]
    assert got["name"] == "Ruth Alvarez" and got["phone"] == f"sim:{uid}" and got["profile"]["needs"] == ["mobility_assist"]
    assert got["home"] == {"lat": 30.0688, "lon": -99.3345} and got["age"] == 78
    real = f"r-{uuid.uuid4().hex[:6]}"
    data.enroll_user(_user(real, simulated=False, phone="+18305550123"))
    with pytest.raises(ValueError):
        data.enroll_user(_user(real, simulated=False, phone="+18305550999"))
    assert {u["id"]: u for u in data.load_users()}[real]["phone"] == "+18305550123"   # no takeover


def test_safety_state_round_trip(data):
    state = {"episode_level": 3, "sent_at": {"3": 10.0}, "mode": "live", "timeline": [[10.0, "danger -> poll"]]}
    data.save_responses([{"user_id": "u1", "episode_level": "danger", "state": state}])
    data.save_tracks([{"user_id": "u1", "motion": {"lat": 30.0, "lon": -99.0, "ts": 1.0, "mode": "live"},
                       "route": ["e1"], "pinged": True}])
    data.save_dangers([{"user_id": "u1", "level": "danger", "hazard_level": "warning", "top_reason": "Water near you",
                        "advice": "move_to_high_ground", "confidence": "medium", "lat": None, "lon": None,
                        "band": "high", "mode": "live", "assessed_at": 1.0}])
    assert data.load_responses()["u1"] == state
    assert data.load_tracks()["u1"]["route"] == ["e1"] and data.load_tracks()["u1"]["pinged"] is True
    data.wipe_runtime("safety")
    assert data.load_responses() == {} and data.load_tracks() == {}


def test_outreach_cases_snapshots_kv(data):
    ev = {"id": uuid.uuid4().hex[:12], "ts": "2026-11-08T10:00:00Z", "driver_id": "u1", "recipient": "driver",
          "channel": "poll", "body": "Are you safe?", "mode": "mock", "status": "sent", "case_id": None}
    data.append_outreach([ev, ev])            # idempotent on id
    if data.name != "file":                   # the file fallback is append-only JSONL (not readable back)
        assert [e["id"] for e in data.list_outreach()].count(ev["id"]) == 1
    data.save_case({"id": "case-1", "driver_id": "u1", "state": "calling", "timeline": []})
    data.save_case({"id": "case-1", "driver_id": "u1", "state": "resolved", "timeline": []})
    assert [c["state"] for c in data.list_cases() if c["id"] == "case-1"] == ["resolved"]
    data.add_snapshot({"point_id": "cp-0014", "drone_id": "d1", "time": "t1", "water_on_road": True})
    assert any(s["point_id"] == "cp-0014" for s in data.list_snapshots())
    data.kv_set("photon2.inbound.cursor", "41")
    data.kv_set("photon2.inbound.cursor", "42")
    assert data.kv_get("photon2.inbound.cursor") == "42" and data.kv_get("missing") is None


# ---- SpacetimeDB-only guarantees ---------------------------------------------------
@pytest.mark.spacetime
def test_private_tables_and_writes_are_owner_only(spacetime_client):
    anon = httpx.Client(base_url="http://127.0.0.1:3000", timeout=5)
    db = spacetime_client.config.database
    for table in ("user_contact", "user_profile", "user_track", "response_state", "outreach_event",
                  "escalation_case", "vision_snapshot", "observation", "raw_record", "kv", "config"):
        r = anon.post(f"/v1/database/{db}/sql", content=f"SELECT * FROM {table}".encode())
        assert r.status_code >= 400 and "private" in r.text, table   # never readable by anyone but the backend
    r = anon.post(f"/v1/database/{db}/call/kv_set", json=["k", "v"])
    assert r.status_code >= 400                            # writes are reserved for the backend's identity
    assert anon.post(f"/v1/database/{db}/sql", content=b"SELECT id FROM source").status_code == 200  # public read ok


@pytest.mark.spacetime
def test_evidence_parity_with_sqlite(spacetime_client, tmp_path):
    """The same observation sequence gives the same revision chain in SQLite and SpacetimeDB."""
    stores = [Store(tmp_path / "e.sqlite3"), SpacetimeEvidenceStore(spacetime_client)]
    rec = f"rec-{uuid.uuid4().hex[:6]}"
    base = {"source_id": "local_reports", "source_record_id": rec, "kind": "report", "observed_at": "2026-11-08T09:00:00Z",
            "geometry": {"type": "Point", "coordinates": [-99.14, 30.05]}, "value": 6.0, "unit": "in", "raw": {"text": "water"}}
    for store in stores:
        first = store.add_observation(base)
        assert store.add_observation({**base, "raw": {**base["raw"], "fetched_at": "later"}})["id"] == first["id"]  # dedupe
        second = store.add_observation({**base, "value": 9.0})
        assert second["supersedes_id"] == first["id"]
        with pytest.raises(ValueError):
            store.add_observation({**base, "value": 12.0, "supersedes_id": first["id"]})   # not the latest revision
        store.save_task({"id": f"t-{rec}", "status": "open", "road_id": "r1"})
        assert any(t["id"] == f"t-{rec}" for t in store.list_tasks())
        store.record_ingestion("usgs_gage", "live", "ok")
        src = {s["id"]: s for s in store.list_sources()}["usgs_gage"]
        assert src["status"] == "live" and src["last_successful_fetch_at"]
    sp = stores[1]
    near = sp.nearby_observations(-99.14, 30.05, 500)
    assert any(o["source_record_id"] == rec for o in near)
    assert not any(o["source_record_id"] == rec for o in sp.nearby_observations(-98.0, 31.0, 500))
    stores[0].close()


@pytest.mark.spacetime
def test_reducer_rejects_bad_input(spacetime_client):
    with pytest.raises(SpacetimeError, match="expected a JSON array|invalid JSON"):
        spacetime_client.call("upsert_dangers", json.dumps({"not": "an array"}))
    with pytest.raises(SpacetimeError, match="unknown scope"):
        spacetime_client.call("wipe_runtime", "everything")
