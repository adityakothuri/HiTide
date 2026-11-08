"""LiveObservations (fake fetchers, no network) and CriticalLoop driven by live frames (TDD)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

import numpy as np
import pytest

from critical.loop import CriticalLoop
from observe.alerts import parse_nws_alerts
from observe.frame import ObservationFrame
from observe.http import Fetched
from observe.live import LiveObservations
from observe.rain import QpeGrid
from sim.region import load_region
from sim.region_flood import RegionFlood

FIX = Path(__file__).parent / "fixtures" / "live"
T0 = datetime(2026, 11, 8, 6, 0, tzinfo=timezone.utc).timestamp()
HUNT_BOX = {"type": "Polygon", "coordinates": [[[-99.40, 30.03], [-99.28, 30.03], [-99.28, 30.10],
                                                [-99.40, 30.10], [-99.40, 30.03]]]}


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()


def warning(id_="w1", geometry=HUNT_BOX, ends=T0 + 3 * 3600, event="Flash Flood Warning"):
    return {"type": "FeatureCollection", "features": [{"id": id_, "type": "Feature", "geometry": geometry, "properties": {
        "id": id_, "event": event, "messageType": "Alert", "status": "Actual", "sent": iso(T0 - 3600),
        "effective": iso(T0 - 3600), "expires": iso(ends), "ends": iso(ends), "headline": "FFW for Kerr County",
        "geocode": {"UGC": ["TXC265"]}, "references": [], "parameters": {}, "areaDesc": "Kerr, TX"}}]}


def flat_series(site_level: float, t_end: float, n: int = 48) -> dict:
    return {"features": [{"properties": {"time": iso(t_end - 300 * k), "value": str(site_level)}} for k in range(n)]}


@pytest.fixture(scope="module")
def region():
    return load_region("hill_country")


@pytest.fixture(scope="module")
def replay_flood(region):
    return RegionFlood(region)


@pytest.fixture(scope="module")
def points():
    data = json.loads((Path(__file__).parents[2] / "data" / "region" / "hill_country" / "nodes.json").read_text())
    return {p["id"]: p for p in data["points"]}


class Clock:
    def __init__(self, t: float):
        self.t = t

    def __call__(self) -> float:
        return self.t


def make_live(region, replay_flood, points, responses: dict, clock: Clock, **kw) -> LiveObservations:
    async def fetch_json(name, url, params=None, timeout_s=10.0):
        r = responses.get(name, responses.get(name.rsplit("_", 1)[0]))
        r = r(name) if callable(r) else r
        return r if isinstance(r, Fetched) else Fetched(None, "none", "http_503")

    static = {s: (i.lon, i.lat) for s, i in replay_flood.info.items()}
    return LiveObservations(region, points, static, replay_flood.celerity, fetch_json=fetch_json, clock=clock, **kw)


# ---- provider -------------------------------------------------------------------
@pytest.mark.asyncio
async def test_alerts_survive_a_failed_fetch_and_age_out_by_their_own_end(region, replay_flood, points):
    responses = {"nws_alerts_tx": Fetched(warning(), "live")}
    clock = Clock(T0)
    live = make_live(region, replay_flood, points, responses, clock)
    await live.refresh("nws_alerts")
    assert [a.id for a in live.frame_at(T0).alerts] == ["w1"]
    assert live.frame_at(T0).sources["nws_alerts"].status == "ok"
    responses["nws_alerts_tx"] = Fetched(None, "none", "http_503")
    await live.refresh("nws_alerts")
    frame = live.frame_at(T0)
    assert [a.id for a in frame.alerts] == ["w1"]                 # outage != "warning cancelled"
    assert frame.sources["nws_alerts"].status == "stale" and frame.sources["nws_alerts"].error == "http_503"
    assert not frame.alerts[0].active_at(T0 + 4 * 3600)          # still ends on its own schedule


@pytest.mark.asyncio
async def test_gauges_build_a_live_flood_and_keep_a_dead_sites_last_series(region, replay_flood, points):
    sites = [g["site"] for g in region.cfg["gauges"]]
    responses = {f"usgs_{s}": Fetched(flat_series(2.0, T0), "live") for s in sites}
    live = make_live(region, replay_flood, points, responses, Clock(T0))
    await live.refresh("usgs_gage")
    f1 = live.frame_at(T0)
    assert f1.flood is not None and f1.hydro_rev == 1
    status = {g["site"]: g for g in f1.flood.gauge_status(T0)}
    assert all(g["online"] and g["stage_ft"] == 2.0 for g in status.values())
    assert f1.flood.celerity == replay_flood.celerity
    await live.refresh("usgs_gage")                               # unchanged data: no rebuild
    assert live.frame_at(T0).hydro_rev == 1
    responses[f"usgs_{sites[0]}"] = Fetched(None, "none", "http_500")
    responses[f"usgs_{sites[1]}"] = Fetched(flat_series(2.5, T0 + 300), "live")
    await live.refresh("usgs_gage")
    f2 = live.frame_at(T0 + 300)
    assert f2.hydro_rev == 2
    st = {g["site"]: g for g in f2.flood.gauge_status(T0 + 300)}
    assert st[sites[0]]["stage_ft"] == 2.0 and st[sites[1]]["stage_ft"] == 2.5
    assert sites[0] in f2.sources["usgs_gage"].error
    # a gauge that stops reporting goes offline by reading age (same 30 min rule as the replay), not at the
    # first failed poll
    late = f2.flood.gauge_status(T0 + 1500)
    assert {g["site"]: g["online"] for g in late}[sites[0]] is True
    later = f2.flood.gauge_status(T0 + 2100)
    assert {g["site"]: g["online"] for g in later}[sites[0]] is False


@pytest.mark.asyncio
async def test_recent_polls_merge_into_the_7_day_history_and_keep_its_baseline(region, replay_flood, points):
    sites = [g["site"] for g in region.cfg["gauges"]]
    week = {"features": [{"properties": {"time": iso(T0 - 3600 * k), "value": "1.0" if k > 100 else "3.0"}}
                         for k in range(160)]}
    responses = {f"usgs_{s}_full": Fetched(week, "live") for s in sites}
    responses.update({f"usgs_{s}_recent": Fetched(flat_series(3.5, T0 + 120, n=3), "live") for s in sites})
    clock = Clock(T0)
    live = make_live(region, replay_flood, points, responses, clock)
    await live.refresh("usgs_gage")                      # first poll: full 7 days
    clock.t = T0 + 120
    await live.refresh("usgs_gage")                      # then recent 3 h, merged
    flood = live.frame_at(clock.t).flood
    g = {x["site"]: x for x in flood.gauge_status(clock.t)}["08166200"]
    assert g["stage_ft"] == 3.5
    assert {x.site: x.base_ft for x in flood.belief_gauges["Guadalupe River"]}["08166200"] == 1.0


@pytest.mark.asyncio
async def test_live_rise_is_measured_from_the_gauges_own_7_day_low(region, replay_flood, points):
    rising = {"features": [{"properties": {"time": iso(T0 - 300 * k), "value": str(1.0 + max(0, 12 - k) * 0.5)}}
                           for k in range(48)]}
    sites = [g["site"] for g in region.cfg["gauges"]]
    responses = {f"usgs_{s}": Fetched(rising if s == "08166200" else flat_series(1.0, T0), "live") for s in sites}
    live = make_live(region, replay_flood, points, responses, Clock(T0))
    await live.refresh("usgs_gage")
    g = {x["site"]: x for x in live.frame_at(T0).flood.gauge_status(T0)}["08166200"]
    assert g["stage_ft"] == 7.0 and g["rate_ft_per_hr"] == 6.0 and g["flood_category"] == "action"
    kerr = live.frame_at(T0).flood.belief_gauges["Guadalupe River"]
    assert {x.site: x.base_ft for x in kerr}["08166200"] == 1.0


@pytest.mark.asyncio
async def test_rain_is_sampled_and_goes_to_no_evidence_when_the_product_is_old(region, replay_flood, points):
    pid, p = next(iter(points.items()))
    values = np.zeros((40, 60))
    west, north = p["lon"] - 0.3, p["lat"] + 0.2
    values[int(0.2 / 0.01), int(0.3 / 0.01)] = 30.0    # 30 mm in the hour at the point
    clock = Clock(T0)

    async def text(url):
        return '<a href="MRMS_RadarOnly_QPE_01H_00.00_20261108-055800.grib2.gz">x</a>'

    async def raw(url):
        assert url.endswith("20261108-055800.grib2.gz")
        return b"grib"

    live = make_live(region, replay_flood, points, {}, clock, fetch_text=text, fetch_bytes=raw,
                     decode_qpe=lambda b, bbox: QpeGrid(values, west, north, 0.01, T0 - 120, "[mm]"))
    await live.refresh("mrms")
    assert live.frame_at(T0).rain_in_hr[pid] == pytest.approx(1.18, abs=0.01)
    assert all(v is None for v in live.frame_at(T0 + 3600).rain_in_hr.values())   # stale grid: no evidence
    assert live.frame_at(T0 + 3600).sources["mrms"].as_of == iso(T0 - 120)


@pytest.mark.asyncio
async def test_nwps_minor_crest_becomes_a_forecast_alert(region, replay_flood, points):
    gauge = json.loads((FIX / "nwps_krrt2.json").read_text())
    fcst = {"issuedTime": iso(T0 - 600), "data": [{"validTime": iso(T0 + 4 * 3600), "primary": 10.4}]}
    responses = {"nwps_KRRT2": Fetched(gauge, "live"), "nwps_KRRT2_fcst": Fetched(fcst, "live"),
                 "nwps_HNTT2": Fetched(None, "none", "http_500"), "nwps_HNTT2_fcst": Fetched(None, "none", "x")}
    live = make_live(region, replay_flood, points, responses, Clock(T0))
    await live.refresh("nwps")
    frame = live.frame_at(T0)
    (a,) = [x for x in frame.alerts if x.level == "forecast"]
    assert "minor" in a.headline and "10.4" in a.headline and not a.is_warning
    assert frame.sources["nwps"].error == "no data: HNTT2"


@pytest.mark.asyncio
async def test_unused_statewide_sources_are_listed_with_reasons(region, replay_flood, points):
    live = make_live(region, replay_flood, points, {}, Clock(T0))
    src = live.frame_at(T0).sources
    assert src["drivetexas_work_zones"].status == "not_used" and "Construction" in src["drivetexas_work_zones"].detail
    assert src["usgs_gage"].status == "pending"
    await live.refresh("usgs_gage")                      # every site fails, nothing cached
    assert live.frame_at(T0).sources["usgs_gage"].status == "unavailable"


# ---- loop in live mode ------------------------------------------------------------
class StaticObs:
    mode = "live"

    def __init__(self, frame: ObservationFrame):
        self.frame = frame

    def frame_at(self, t: float) -> ObservationFrame:
        return self.frame


def test_loop_live_frame_warning_is_per_point_closure_confirms_and_drones_do_not_fly(region, replay_flood):
    sites = {g["site"] for g in region.cfg["gauges"]}
    static = {s: (i.lon, i.lat) for s, i in replay_flood.info.items()}
    from observe.gauges import build_hydro, usgs_series
    hydro = build_hydro({s: usgs_series(flat_series(1.0, T0)) for s in sites}, static)
    flood = RegionFlood(region, hydro, baseline="window_min", celerity=replay_flood.celerity, max_gap_s=2700)
    alerts = parse_nws_alerts(warning())
    loop = CriticalLoop(region, flood, simulate_drones=False,
                        observations=StaticObs(ObservationFrame(mode="live")))
    pts = loop.points
    hunt = [pid for pid, p in pts.items() if alerts[0].covers(p["lon"], p["lat"], loop.region_zones)]
    kerr = [pid for pid, p in pts.items() if pid not in hunt]
    assert hunt and kerr
    closed = kerr[0]
    loop.observations = StaticObs(ObservationFrame(mode="live", hydro_rev=1, flood=flood, alerts=alerts,
                                                   closures=MappingProxyType({closed: "storm report"})))
    events = loop.step(T0)
    assert any(k == "region.alert" and p["active"] and not p["simulated"] for k, p in events)
    assert all(loop.p[pid] >= 0.30 for pid in hunt)                       # inside the polygon
    assert all(loop.p[pid] <= 0.02 for pid in kerr if pid != closed)      # same county, outside the polygon
    assert loop.status[closed] == "confirmed_flooded"
    for _ in range(20):
        events = loop.step(T0 + 60 * (_ + 1))
        assert not any(k == "snapshot.created" for k, _p in events)
    assert all(d.state == "idle" for d in loop.drones.values())
    assert any(d.tour for d in loop.drones.values())                      # tours are planned, not flown
    assert loop.snapshot["mode"] == "live"
    # the warning ends: one inactive event, flights stop
    loop.observations = StaticObs(ObservationFrame(mode="live", hydro_rev=1, flood=flood))
    events = loop.step(T0 + 4 * 3600)
    assert [p["active"] for k, p in events if k == "region.alert"] == [False]
    assert not loop.warnings and all(not d.tour for d in loop.drones.values())


def test_loop_replay_frame_matches_the_old_global_warning(region, replay_flood):
    loop = CriticalLoop(region, replay_flood)
    t = datetime.fromisoformat("2025-07-04T01:20:00-05:00").timestamp()
    loop.step(t)
    assert loop.warnings and all(loop.p[pid] >= 0.30 for pid in loop.points)   # county-wide: every point
    assert loop.snapshot["mode"] == "replay" and loop.alerts[0]["simulated"] is True


def test_single_bad_low_reading_does_not_set_the_baseline():
    from sim.region_flood import _despiked_min
    assert _despiked_min(np.array([2.0, 2.0, -5.0, 2.0, 2.1, 1.9, 1.9])) == 1.9
