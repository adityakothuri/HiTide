from sim.drivers import Contact, Driver, Route, Vehicle
from stages.route_check import Hazard, lookahead, plan_pretrip, route_hits

STATUS = {"2-3-0": "closed", "3-4-0": "caution", "9-9-0": "boat"}


def drv(id_="d1", age=40, edges=("1-2-0", "2-3-0", "3-4-0"), parent=False):
    p = Contact("P", "parent", "env:DEMO_PHONE_A") if parent else None
    return Driver(id=id_, name=id_, age=age, vehicle=Vehicle("a", "b", "sedan"), home_node=1, phone="x",
                  emergency_contact=Contact("E", "spouse", "y"), routes=(Route("work", 4, edges, 300.0),), parent=p)


def test_route_hits_returns_closed_and_at_risk_in_route_order():
    hits = route_hits(("1-2-0", "2-3-0", "3-4-0"), STATUS)
    assert [(h.edge_id, h.status) for h in hits] == [("2-3-0", "closed"), ("3-4-0", "caution")]


def test_route_hits_empty_when_route_dry():
    assert route_hits(("1-2-0", "5-6-0"), STATUS) == ()


def test_plan_warns_parked_driver_whose_route_crosses_closed_road():
    out = plan_pretrip([drv()], STATUS, moving=frozenset(), already=frozenset(), alert_id="a1")
    assert [w.driver_id for w in out] == ["d1"]
    assert out[0].blocking is True


def test_plan_never_warns_moving_driver():
    assert plan_pretrip([drv()], STATUS, moving=frozenset({"d1"}), already=frozenset(), alert_id="a1") == []


def test_plan_dedupes_per_driver_per_alert():
    assert plan_pretrip([drv()], STATUS, moving=frozenset(), already=frozenset({("d1", "a1")}), alert_id="a1") == []
    assert len(plan_pretrip([drv()], STATUS, moving=frozenset(), already=frozenset({("d1", "a0")}), alert_id="a1")) == 1


def test_caution_only_route_warns_but_not_blocking():
    out = plan_pretrip([drv(edges=("1-2-0", "3-4-0"))], STATUS, moving=frozenset(), already=frozenset(), alert_id="a1")
    assert out[0].blocking is False


def test_dry_route_gets_no_warning():
    assert plan_pretrip([drv(edges=("1-2-0",))], STATUS, moving=frozenset(), already=frozenset(), alert_id="a1") == []


def test_teen_warning_copies_parent():
    out = plan_pretrip([drv(age=17, parent=True)], STATUS, moving=frozenset(), already=frozenset(), alert_id="a1")
    assert out[0].notify_parent is True
    assert plan_pretrip([drv()], STATUS, frozenset(), frozenset(), "a1")[0].notify_parent is False


def test_lookahead_finds_first_closed_edge_within_distance():
    ahead = [("1-2-0", 0.0), ("2-3-0", 150.0), ("9-9-0", 400.0)]
    h = lookahead(ahead, STATUS, lookahead_m=800)
    assert h == Hazard(edge_id="2-3-0", status="closed", distance_m=150.0)


def test_lookahead_ignores_caution_and_far_hazards():
    ahead = [("3-4-0", 10.0), ("9-9-0", 900.0)]
    assert lookahead(ahead, STATUS, lookahead_m=800) is None
