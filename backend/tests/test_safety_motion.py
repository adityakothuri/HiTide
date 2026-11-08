"""Location pings -> parked / driving / stopped, robust to GPS jitter and out-of-order pings."""

from safety.motion import Ping, bearing_deg, haversine_m, update

M = 1 / 111_000  # ~1 m of latitude in degrees


def run(pings):
    s = None
    for p in pings:
        s = update(s, p)
    return s


def test_first_ping_parked_or_driving():
    assert run([Ping(30.0, -99.0, 0)]).state == "parked"
    assert run([Ping(30.0, -99.0, 0, speed_mps=15)]).state == "driving"


def test_gps_jitter_while_parked_never_drives_or_walks():
    pings = [Ping(30.0 + (8 * M if k % 2 else -8 * M), -99.0, k * 10) for k in range(30)]
    s = run(pings)
    assert s.state == "parked" and s.speed_mps == 0.0
    assert haversine_m(s.lat, s.lon, 30.0 - 8 * M, -99.0) < 1.0  # kept the first fix


def test_reported_accuracy_widens_the_noise_floor():
    s = run([Ping(30.0, -99.0, 0), Ping(30.0 + 40 * M, -99.0, 2, accuracy_m=50)])
    assert s.state == "parked"


def test_derived_speed_and_heading_when_phone_gives_none():
    s = run([Ping(30.0, -99.0, 0), Ping(30.0 + 200 * M, -99.0, 10)])
    assert s.state == "driving" and 15 < s.speed_mps < 25
    assert s.heading_deg is not None and (s.heading_deg < 5 or s.heading_deg > 355)  # north


def test_stopped_after_driving_then_parked_later():
    s = run([Ping(30.0, -99.0, 0, speed_mps=15), Ping(30.001, -99.0, 30, speed_mps=0)])
    assert s.state == "stopped" and s.stopped_for(90) == 60
    s = update(s, Ping(30.001, -99.0, 30 + 700, speed_mps=0))
    assert s.state == "parked"


def test_out_of_order_and_duplicate_pings_ignored():
    a = run([Ping(30.0, -99.0, 100, speed_mps=15)])
    assert update(a, Ping(31.0, -98.0, 50, speed_mps=0)) is a
    assert update(a, Ping(31.0, -98.0, 100, speed_mps=0)) is a


def test_geometry_helpers():
    assert abs(haversine_m(30.0, -99.0, 30.0 + 1000 * M, -99.0) - 1000) < 5
    assert 85 < bearing_deg(30.0, -99.0, 30.0, -98.99) < 95
