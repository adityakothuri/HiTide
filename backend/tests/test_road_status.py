import pytest

from scoring.road_status import RoadStatus, classify


@pytest.mark.parametrize(
    ("depth_in", "expected"),
    [
        (0.0, RoadStatus.OPEN),
        (2.9, RoadStatus.OPEN),
        (3.0, RoadStatus.CAUTION),
        (5.99, RoadStatus.CAUTION),
        (6.0, RoadStatus.CLOSED),
        (11.9, RoadStatus.CLOSED),
        (12.0, RoadStatus.FLOAT),
        (23.9, RoadStatus.FLOAT),
        (24.0, RoadStatus.BOAT),
        (60.0, RoadStatus.BOAT),
    ],
)
def test_classify_thresholds_match_nws_table(depth_in, expected):
    assert classify(depth_in) is expected


def test_negative_depth_is_open():
    assert classify(-4.0) is RoadStatus.OPEN


def test_custom_thresholds_override_defaults():
    t = {"caution": 1, "closed": 2, "float": 3, "boat": 4}
    assert classify(2.5, t) is RoadStatus.CLOSED


@pytest.mark.parametrize(
    ("status", "passable"),
    [
        (RoadStatus.OPEN, True),
        (RoadStatus.CAUTION, True),
        (RoadStatus.CLOSED, False),
        (RoadStatus.FLOAT, False),
        (RoadStatus.BOAT, False),
    ],
)
def test_passable_for_cars(status, passable):
    assert status.passable_for_cars is passable


def test_truck_passable_below_boat_only():
    assert RoadStatus.FLOAT.passable_for_trucks is True
    assert RoadStatus.BOAT.passable_for_trucks is False
