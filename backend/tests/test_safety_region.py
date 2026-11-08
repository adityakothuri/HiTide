"""Integration on the real Hill Country region: locator, danger, monitor, and the July 4, 2025 replay."""

import asyncio
from dataclasses import replace

import numpy as np
import pytest
from shapely.geometry import box

from critical.loop import CriticalLoop
from observe.alerts import Alert
from safety.context import build_context, empty_context
from safety.danger import assess_user
from safety.hazard import Locator, assess
from safety.levels import Level
from safety.monitor import SafetyMonitor
from safety.motion import MotionState, Ping
from safety.users import SafetyUser, UserRegistry
from sim.region import load_region
from sim.region_flood import RegionFlood, epoch

pytest.importorskip("osmnx")


@pytest.fixture(scope="module")
def world():
    region = load_region("hill_country")
    loop = CriticalLoop(region, RegionFlood(region))
    return region, loop, Locator(region, loop.points)


def _edge_with_mid(region, loc, min_hand=None):
    """A long-ish edge whose midpoint snaps back to itself."""
    for i, f in enumerate(region.segments_fc["features"]):
        if f["properties"]["length_m"] < 150:
            continue
        lon, lat = region.mid[i]
        if loc.nearest_edge(lat, lon)[0] != i:
            continue
        if min_hand is not None and not (np.isfinite(loc.hand[i]) and loc.hand[i] < min_hand):
            continue
        return i, float(lat), float(lon)
    raise AssertionError("no edge found")


def _ctx(region, t=1.0e9, wet=None, known_all=True, alerts=()):
    ctx = empty_context(len(region.edge_ids))
    belief = np.zeros(len(region.edge_ids))
    known = np.full(len(region.edge_ids), known_all)
    for i, d in (wet or {}).items():
        belief[i], known[i] = d, True
    return replace(ctx, t=t, belief_in=belief, known=known, alerts=tuple(alerts),
                   region_zones=frozenset(region.cfg["nws_zones"]))


def _user(uid="u1", lat=30.05, lon=-99.2, needs=(), age=40, phone=None, stall=12):
    prof = {"consent": {"flood_alerts": True}, "needs": list(needs), "policy": {"stall_depth_in": stall}}
    return SafetyUser(uid, "Test User", age, phone or f"sim:{uid}", lat, lon, "Contact", f"sim:{uid}-c", None, prof)


def test_depth_at_your_road_and_unknown_is_none(world):
    region, _, loc = world
    i, lat, lon = _edge_with_mid(region, loc)
    h = assess(loc, _ctx(region, wet={i: 14.0}), lat, lon)
    assert h.edge_id == region.edge_ids[i] and h.depth_in == pytest.approx(14.0)
    h2 = assess(loc, _ctx(region, known_all=False), lat, lon)
    assert h2.depth_in is None and h2.unknown_nearby


def test_outside_region_only_polygon_alerts(world):
    region, _, loc = world
    zone_alert = Alert("a1", "Flash Flood Warning", "warning", "FFW Kerr", 0.0, None, zones=frozenset({"TXC265"}))
    poly_alert = Alert("a2", "Flash Flood Warning", "warning", "FFW Bexar", 0.0, None,
                       geometry=box(-98.6, 29.3, -98.4, 29.5))
    ctx = _ctx(region, alerts=(zone_alert, poly_alert))
    far = assess(loc, ctx, 29.4, -98.5)
    assert far.coverage == "alerts_only" and far.in_warning and far.alert_headlines == ("FFW Bexar",)
    assert not assess(loc, ctx, 31.0, -97.0).in_warning                  # zone alert never leaks outside
    assert assess(loc, ctx, 30.05, -99.2).in_warning                     # inside region: zone applies


def test_stopped_in_water_is_critical(world):
    region, _, loc = world
    i, lat, lon = _edge_with_mid(region, loc)
    ctx = _ctx(region, t=1000.0, wet={i: 4.0})
    m = MotionState(lat, lon, 1000.0, "stopped", 0.0, None, still_since=900.0, last_moving_ts=880.0)
    a = assess_user(loc, ctx, "u1", {"policy": {"stall_depth_in": 24}}, 40, m, 1000.0)
    assert a.level == Level.CRITICAL and a.stopped_in_water and a.reasons[0].startswith("Your vehicle has been stopped")
    parked = replace(m, state="parked", last_moving_ts=None)
    assert assess_user(loc, ctx, "u1", {"policy": {"stall_depth_in": 24}}, 40, parked, 1000.0).level == Level.WARNING


def test_vulnerability_bumps_but_never_invents(world):
    region, _, loc = world
    i, lat, lon = _edge_with_mid(region, loc)
    m = MotionState(lat, lon, 1000.0, "parked")
    wet = _ctx(region, t=1000.0, wet={i: 4.0})
    dry = _ctx(region, t=1000.0)
    needs = {"needs": ["wheelchair_user"], "policy": {"stall_depth_in": 24}}
    assert assess_user(loc, wet, "u", needs, 40, m, 1000.0).level == Level.DANGER
    a = assess_user(loc, dry, "u", needs, 40, m, 1000.0)
    assert a.level == Level.NONE and not a.bumped


def test_water_ahead_while_driving(world):
    region, _, loc = world
    i, lat, lon = _edge_with_mid(region, loc)
    near = {e: d for e, d in loc.edges_within(lat, lon, 700).items() if d > 250}
    j = next(iter(near))
    jlon, jlat = region.mid[j]
    import math
    heading = math.degrees(math.atan2((jlon - lon) * math.cos(math.radians(lat)), jlat - lat)) % 360
    ctx = _ctx(region, t=1000.0, wet={j: 9.0})
    m = MotionState(lat, lon, 1000.0, "driving", 15.0, heading, None, 1000.0)
    a = assess_user(loc, ctx, "u", {"policy": {"stall_depth_in": 24}}, 40, m, 1000.0)
    assert a.hazard.ahead and a.advice == "turn_around" and a.level >= Level.WARNING
    away = replace(m, heading_deg=(heading + 180) % 360)
    assert not assess_user(loc, ctx, "u", {"policy": {"stall_depth_in": 24}}, 40, away, 1000.0).hazard.ahead


def test_planned_route_snaps_and_flags(world):
    region, _, loc = world
    i, lat, lon = _edge_with_mid(region, loc)
    coords = [tuple(c[::-1]) for c in region.segments_fc["features"][i]["geometry"]["coordinates"]]
    edges = loc.snap_route(coords)
    assert i in edges
    h = assess(loc, _ctx(region, wet={i: 5.0}), 30.0, -99.44, route_edges=edges)
    assert h.route and h.route[0].edge_id == region.edge_ids[i]


def test_monitor_ping_reply_and_phone_match(world, monkeypatch):
    region, _, loc = world
    monkeypatch.setenv("DEMO_PHONE_B", "+18305550199")
    i, lat, lon = _edge_with_mid(region, loc)
    users = UserRegistry([_user("u1", lat, lon, phone="env:DEMO_PHONE_B")], registry_path=None)
    events = []

    async def emit(t, p):
        events.append((t, p))

    class Out:
        sent = []

        async def send(self, msg):
            self.sent.append(msg)
            return {"status": "sent"}

    m = SafetyMonitor(loc, users, Out(), emit, state_path=None)
    m.ctx = _ctx(region, t=5000.0, wet={i: 8.0})
    d = m.ping("u1", Ping(lat, lon, 0.0))
    assert d.assessment.level == Level.DANGER and [a.kind for a in d.actions] == ["poll"]
    asyncio.run(m.dispatch([d]))
    assert Out.sent[0].channel == "poll" and Out.sent[0].phone == "env:DEMO_PHONE_B"
    assert events[0][0] == "user.danger" and "phone" not in str(events[0][1]["user"])
    hit = m.find_by_phone("(830) 555-0199")
    assert hit is not None and hit[0].id == "u1" and hit[1] == "driver"
    acts = m.reply("u1", "safe", "driver")
    assert [a.template for a in acts] == ["ack_safe"]
    assert m.refresh()[0].actions == ()     # muted: nothing new
    with pytest.raises(KeyError):
        m.ping("nobody", Ping(lat, lon, 0.0))


def test_replay_finds_ruth_in_danger_before_the_emergency(world):
    """July 4, 2025: Ruth (78, mobility need, Hunt, South Fork) is at least DANGER by 04:15 CDT, well before the
    04:22 SH 39 checkpoint, from belief only (warnings, gauges, unknown crossings)."""
    region, loop, loc = world
    users = UserRegistry.load(registry=None)
    ruth = users.get("hc-ruth")
    if ruth is None:
        pytest.skip("data/region_users.json missing")
    loop.reset_state()
    for hhmm in ("01:00", "01:20", "04:15"):
        loop.step(epoch(f"2025-07-04T{hhmm}:00-05:00"))
    ctx = build_context(loop)
    m = MotionState(ruth.home_lat, ruth.home_lon, ctx.t, "parked")
    a = assess_user(loc, ctx, ruth.id, ruth.profile, ruth.age, m, ctx.t)
    assert a.level >= Level.DANGER and a.bumped
    loop.reset_state()
