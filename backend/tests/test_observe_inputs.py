"""Live inputs -> observation values: MRMS rain sampling, USGS series, NWPS forecasts, storm-report closures (TDD)."""

import json
from datetime import datetime
from pathlib import Path

import numpy as np

from observe.gauges import build_hydro, flood_category, parse_nwps, usgs_series
from observe.rain import QpeGrid, sample_points
from observe.reports import lsr_closures

FIX = Path(__file__).parent / "fixtures" / "live"
MM = 25.4


def ts(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


# ---- MRMS ------------------------------------------------------------------
def grid(values: np.ndarray) -> QpeGrid:
    return QpeGrid(values=values.astype(float), west=-99.50, north=30.20, res=0.01, valid_t=0.0, unit="[mm]")


def test_rain_sampled_at_point_converted_to_inches_with_neighbourhood_max():
    v = np.zeros((30, 50))
    v[10, 20] = 2 * MM            # lon -99.295, lat 30.095
    pts = {"hit": (-99.295, 30.095), "next_to_it": (-99.285, 30.095), "far": (-98.90, 30.00)}
    out = sample_points(grid(v), pts)
    assert out["hit"] == 2.0 and out["next_to_it"] == 2.0   # 1-pixel (~1 km) tolerance for point location
    assert out["far"] is None                                # outside the decoded window: no evidence, not dry


def test_rain_sentinels_are_missing_not_zero():
    v = np.full((30, 50), -3.0)
    v[0, 0] = 0.0
    out = sample_points(grid(v), {"missing": (-99.25, 30.05), "dry": (-99.495, 30.195)})
    assert out["missing"] is None and out["dry"] == 0.0


# ---- USGS ------------------------------------------------------------------
def test_usgs_series_sorted_numeric_and_deduplicated():
    payload = {"features": [
        {"properties": {"time": "2026-11-08T02:10:00+00:00", "value": "1.50"}},
        {"properties": {"time": "2026-11-08T02:00:00+00:00", "value": "1.40"}},
        {"properties": {"time": "2026-11-08T02:00:00+00:00", "value": "1.40"}},
        {"properties": {"time": "2026-11-08T02:05:00+00:00", "value": "Eqp"}},
        {"properties": {"time": None, "value": "2"}}, None]}
    assert usgs_series(payload) == [("2026-11-08T02:00:00+00:00", 1.4), ("2026-11-08T02:10:00+00:00", 1.5)]


def test_real_usgs_payload():
    s = usgs_series(json.loads((FIX / "usgs_08166200_6h.json").read_text()))
    assert len(s) > 30 and all(isinstance(v, float) for _, v in s)
    assert [t for t, _ in s] == sorted(t for t, _ in s)


def test_build_hydro_keeps_every_configured_site_even_without_data():
    static = {"A": (-99.3, 30.0), "B": (-99.2, 30.1)}
    hydro = build_hydro({"A": [("2026-11-08T02:00:00+00:00", 1.0)]}, static)
    assert hydro["A"]["series"] == [["2026-11-08T02:00:00+00:00", 1.0]]
    assert hydro["B"] == {"lon": -99.2, "lat": 30.1, "series": []}


# ---- NWPS ------------------------------------------------------------------
CATS = {"action": 7, "minor": 9, "moderate": 12, "major": 20}


def test_flood_category():
    assert flood_category(6.9, CATS) == "none"
    assert flood_category(9.0, CATS) == "minor"
    assert flood_category(25, CATS) == "major"
    assert flood_category(None, CATS) is None


def test_nwps_forecast_crest_from_real_payload():
    f = parse_nwps(json.loads((FIX / "nwps_krrt2.json").read_text()),
                   json.loads((FIX / "nwps_krrt2_forecast.json").read_text()), site="08166200")
    assert f.lid == "KRRT2" and f.site == "08166200"
    assert f.observed_ft == 1.44 and f.observed_category == "none"
    assert f.crest_ft == 1.2 and f.crest_category == "none" and f.crest_at is not None
    assert f.thresholds == {"action": 7.0, "minor": 9.0, "moderate": 12.0, "major": 20.0}


def test_nwps_missing_forecast_is_none_not_zero():
    gauge = json.loads((FIX / "nwps_krrt2.json").read_text())
    f = parse_nwps(gauge, {"data": []}, site="08166200")
    assert f.crest_ft is None and f.crest_category is None
    f = parse_nwps(gauge, {"data": [{"validTime": "2026-11-08T05:00:00Z", "primary": -999}]}, site="08166200")
    assert f.crest_ft is None


def test_nwps_forecast_crest_picks_the_max():
    gauge = json.loads((FIX / "nwps_krrt2.json").read_text())
    fcst = {"data": [{"validTime": "2026-11-08T05:00:00Z", "primary": 4.0},
                     {"validTime": "2026-11-08T09:00:00Z", "primary": 10.5},
                     {"validTime": "2026-11-08T12:00:00Z", "primary": 8.0}]}
    f = parse_nwps(gauge, fcst, site="08166200")
    assert f.crest_ft == 10.5 and f.crest_category == "minor" and f.crest_at == "2026-11-08T09:00:00Z"


# ---- Local storm reports -----------------------------------------------------
POINTS = {"cp-1": {"lon": -99.335, "lat": 30.071, "name": "State Highway 39"},
          "cp-2": {"lon": -99.14, "lat": 30.05, "name": "Junction Highway"}}
NOW = ts("2026-07-04T05:00:00-05:00")


def lsr(lon, lat, remark, typetext="FLASH FLOOD", valid="2026-07-04T09:30:00Z", state="TX"):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"valid": valid, "typetext": typetext, "state": state, "remark": remark,
                           "city": "Hunt", "county": "Kerr", "wfo": "EWX"}}


def test_road_flood_report_near_a_point_is_a_closure():
    out = lsr_closures({"features": [lsr(-99.336, 30.0712, "Water over SH 39, road impassable.")]}, POINTS, NOW)
    assert list(out) == ["cp-1"] and "SH 39" in out["cp-1"]


def test_reports_far_away_old_non_flood_or_without_road_are_ignored():
    feats = [lsr(-99.30, 30.071, "Water over SH 39."),                                  # ~3 km away
             lsr(-99.335, 30.071, "Water over SH 39.", valid="2026-07-03T22:00:00Z"),    # 6 h old
             lsr(-99.335, 30.071, "Water over SH 39.", typetext="HAIL"),
             lsr(-99.335, 30.071, "Creek out of its banks behind a home."),
             lsr(-99.335, 30.071, "Water over SH 39.", valid="2026-07-04T11:30:00Z")]    # in the future
    assert lsr_closures({"features": feats}, POINTS, NOW) == {}
    assert lsr_closures(None, POINTS, NOW) == {}


def test_receded_or_reopened_reports_are_not_closures():
    feats = [lsr(-99.335, 30.071, "Water has receded from SH 39."), lsr(-99.335, 30.071, "SH 39 reopened.")]
    assert lsr_closures({"features": feats}, POINTS, NOW) == {}


def test_not_current_nwps_forecast_has_no_crest():
    gauge = json.loads((FIX / "nwps_krrt2.json").read_text())
    gauge = {**gauge, "status": {**gauge["status"], "forecast": {"floodCategory": "fcst_not_current"}}}
    f = parse_nwps(gauge, {"data": [{"validTime": "2026-11-08T09:00:00Z", "primary": 10.5}]}, site="08166200")
    assert f.crest_ft is None
