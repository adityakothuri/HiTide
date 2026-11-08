"""The outreach ladder survives a backend restart in live mode (no duplicate alerts); replay resets clear it."""

import asyncio
from dataclasses import replace

import numpy as np
import pytest

from critical.loop import CriticalLoop
from db.factory import open_database
from safety.context import empty_context
from safety.hazard import Locator
from safety.levels import Level
from safety.monitor import SafetyMonitor
from safety.motion import Ping
from safety.users import SafetyUser, UserRegistry
from sim.region import load_region
from sim.region_flood import RegionFlood

pytest.importorskip("osmnx")


@pytest.fixture(scope="module")
def world():
    region = load_region("hill_country")
    loop = CriticalLoop(region, RegionFlood(region))
    loc = Locator(region, loop.points)
    i = next(k for k in range(len(region.edge_ids))
             if region.segments_fc["features"][k]["properties"]["length_m"] > 150
             and loc.nearest_edge(region.mid[k][1], region.mid[k][0])[0] == k)
    return region, loc, i


class Out:
    def __init__(self):
        self.sent = []

    async def send(self, msg):
        self.sent.append(msg)
        return {"status": "sent"}


async def _emit(*_a):
    return None


def _monitor(loc, region, i, db, now):
    lon, lat = region.mid[i]
    user = SafetyUser("u1", "Ruth Alvarez", 78, "sim:u1", float(lat), float(lon),
                      profile={"consent": {"flood_alerts": True}, "policy": {"stall_depth_in": 24}})
    m = SafetyMonitor(loc, UserRegistry([user], registry_path=None), Out(), _emit, state_path=None,
                      clock=lambda: now, db=db)
    m.reset("live")
    belief = np.zeros(len(region.edge_ids))
    belief[i] = 8.0
    m.ctx = replace(empty_context(len(region.edge_ids), "live"), t=now, belief_in=belief,
                    known=np.ones(len(region.edge_ids), dtype=bool))
    return m, float(lat), float(lon)


def test_ladder_survives_restart_without_duplicate_alerts(world, tmp_path, monkeypatch):
    region, loc, i = world
    monkeypatch.setenv("HITIDE_DB_PATH", str(tmp_path / "e.sqlite3"))
    db = open_database("memory")
    try:
        m1, lat, lon = _monitor(loc, region, i, db, now=1000.0)
        d = m1.ping("u1", Ping(lat, lon, 1000.0))
        assert d.assessment.level == Level.DANGER and [a.kind for a in d.actions] == ["poll"]
        assert db.writer.flush()
        assert db.data.load_responses()["u1"]["episode_level"] == int(Level.DANGER)
        assert db.data.dangers["u1"]["level"] == "danger" and db.data.dangers["u1"]["lat"] is not None  # simulated user

        m2, _, _ = _monitor(loc, region, i, db, now=1010.0)        # "restart": a brand-new monitor, same database
        assert m2.tracks["u1"].response.episode_level == Level.DANGER
        assert m2.tracks["u1"].motion is not None                   # last position restored too
        d2 = m2.refresh()[0]
        assert d2.assessment.level == Level.DANGER and d2.actions == ()   # no second poll after the restart
    finally:
        db.close()


def test_replay_reset_clears_persisted_ladders(world, tmp_path, monkeypatch):
    region, loc, i = world
    monkeypatch.setenv("HITIDE_DB_PATH", str(tmp_path / "e.sqlite3"))
    db = open_database("memory")
    try:
        m, lat, lon = _monitor(loc, region, i, db, now=1000.0)
        m.ping("u1", Ping(lat, lon, 1000.0))
        m.reset("replay")
        assert db.writer.flush()
        assert db.data.load_responses() == {} and db.data.load_tracks() == {}
    finally:
        db.close()
