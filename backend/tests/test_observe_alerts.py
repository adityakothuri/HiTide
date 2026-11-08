"""NWS CAP alerts -> detection alerts: level, validity, supersession, region coverage (TDD)."""

import json
from datetime import datetime
from pathlib import Path

from observe.alerts import parse_nws_alerts, region_alerts

FIX = Path(__file__).parent / "fixtures" / "live"
KERR_ZONES = frozenset({"TXC265", "TXZ186"})
BBOX = {"west": -99.45, "south": 29.97, "east": -99.10, "north": 30.12}


def ts(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


def feature(id_, event="Flash Flood Warning", mtype="Alert", sent="2026-11-08T01:00:00-06:00",
            expires="2026-11-08T04:00:00-06:00", ends=None, geometry=None, ugc=("TXC265",), refs=(), status="Actual",
            headline=None, parameters=None):
    return {"id": id_, "type": "Feature", "geometry": geometry, "properties": {
        "id": id_, "event": event, "messageType": mtype, "status": status, "sent": sent, "effective": sent,
        "expires": expires, "ends": ends, "headline": headline or f"{event} issued", "severity": "Severe",
        "geocode": {"UGC": list(ugc)}, "references": [{"identifier": r} for r in refs],
        "parameters": parameters or {}, "areaDesc": "Kerr, TX"}}


def fc(*features):
    return {"type": "FeatureCollection", "features": list(features)}


HUNT_BOX = {"type": "Polygon", "coordinates": [[[-99.40, 30.03], [-99.28, 30.03], [-99.28, 30.10],
                                                [-99.40, 30.10], [-99.40, 30.03]]]}


def test_levels_and_non_flood_events_dropped():
    alerts = parse_nws_alerts(fc(feature("a"), feature("b", event="Flood Watch"), feature("c", event="Flood Advisory"),
                                 feature("d", event="Rip Current Statement"), feature("e", event="Flood Statement")))
    assert {a.id: a.level for a in alerts} == {"a": "warning", "b": "watch", "c": "advisory", "e": "statement"}


def test_tests_exercises_and_cancels_are_dropped_and_cancel_removes_its_reference():
    alerts = parse_nws_alerts(fc(feature("a"), feature("t", status="Test"),
                                 feature("x", mtype="Cancel", refs=("a",))))
    assert alerts == ()


def test_update_supersedes_the_alert_it_references():
    alerts = parse_nws_alerts(fc(feature("a", expires="2026-11-08T03:00:00-06:00"),
                                 feature("a2", mtype="Update", refs=("a",), expires="2026-11-08T05:00:00-06:00")))
    assert [a.id for a in alerts] == ["a2"]
    assert alerts[0].expires == ts("2026-11-08T05:00:00-06:00")


def test_validity_uses_event_end_not_message_expiry():
    (a,) = parse_nws_alerts(fc(feature("w", event="Flood Watch", expires="2026-11-08T06:00:00-06:00",
                                       ends="2026-11-09T09:00:00-06:00")))
    assert a.active_at(ts("2026-11-08T08:00:00-06:00"))       # message expired, event still on
    assert not a.active_at(ts("2026-11-09T09:00:00-06:00"))    # event over
    assert not a.active_at(ts("2026-11-08T00:59:00-06:00"))    # not yet effective


def test_issued_hours_ago_still_counts_for_detection():
    (a,) = parse_nws_alerts(fc(feature("a", sent="2026-11-08T01:00:00-06:00", expires="2026-11-08T07:00:00-06:00")))
    assert a.active_at(ts("2026-11-08T04:00:00-06:00"))


def test_polygon_coverage_is_exact_and_zones_only_used_without_polygon():
    (poly,) = parse_nws_alerts(fc(feature("p", geometry=HUNT_BOX)))
    assert poly.covers(-99.33, 30.07, KERR_ZONES)          # Hunt
    assert not poly.covers(-99.14, 30.05, KERR_ZONES)      # Kerrville: same county, outside the polygon
    (zone,) = parse_nws_alerts(fc(feature("z", event="Flood Watch", ugc=("TXZ186",))))
    assert zone.covers(-99.14, 30.05, KERR_ZONES)
    (other,) = parse_nws_alerts(fc(feature("o", ugc=("TXC019",))))
    assert not other.covers(-99.14, 30.05, KERR_ZONES)


def test_flash_flood_emergency_is_flagged():
    (a,) = parse_nws_alerts(fc(feature("e", parameters={"flashFloodDamageThreat": ["CATASTROPHIC"]})))
    assert a.emergency and a.level == "warning"


def test_region_filter_keeps_only_alerts_touching_the_region():
    far = {"type": "Polygon", "coordinates": [[[-97, 30], [-96.9, 30], [-96.9, 30.1], [-97, 30]]]}
    alerts = parse_nws_alerts(fc(feature("in", geometry=HUNT_BOX), feature("far", geometry=far, ugc=("TXC265",)),
                                 feature("zone", event="Flood Watch", ugc=("TXZ186",)),
                                 feature("nozone", event="Flood Watch", ugc=("TXZ252",))))
    assert [a.id for a in region_alerts(alerts, BBOX, KERR_ZONES)] == ["in", "zone"]


def test_real_texas_payload_parses():
    alerts = parse_nws_alerts(json.loads((FIX / "nws_active_tx.json").read_text()))
    assert alerts and all(a.level in ("watch", "advisory", "warning", "statement") for a in alerts)
    assert all(a.source == "nws" and not a.simulated for a in alerts)
    bandera = [a for a in alerts if "TXC019" in a.zones and a.geometry is not None]
    assert bandera and not any(a.covers(-99.14, 30.05, KERR_ZONES) for a in bandera)


def test_malformed_features_are_skipped_not_fatal():
    bad = {"id": "bad", "properties": {"event": "Flood Warning", "status": "Actual", "messageType": "Alert",
                                       "sent": "not a time"}}
    assert parse_nws_alerts({"features": [bad, None, 3]}) == ()
    assert parse_nws_alerts(None) == ()


def test_statement_continuing_a_warning_stays_a_warning():
    alerts = parse_nws_alerts(fc(feature("w"), feature("s", event="Flash Flood Statement", mtype="Update", refs=("w",))))
    assert [(a.id, a.level) for a in alerts] == [("s", "warning")]
