import pytest

from vision.assess import assess, people_placement

CAR = [100, 200, 300, 300]  # x1, y1, x2, y2 (car top at y=200, height 100)
IMG_H = 1000


def test_standing_on_roof():
    assert people_placement([180, 120, 220, 215], [CAR], IMG_H) == "on_roof"


def test_seated_on_roof_legs_over_windshield():
    assert people_placement([180, 160, 230, 250], [CAR], IMG_H) == "on_roof"


def test_mostly_inside_car_box_is_inside_unknown():
    assert people_placement([150, 240, 200, 295], [CAR], IMG_H) == "inside_unknown"


def test_away_from_car_is_in_water():
    assert people_placement([600, 300, 640, 400], [CAR], IMG_H) == "in_water"


def test_bottom_band_is_on_shore_heuristic():
    assert people_placement([600, 900, 640, 995], [CAR], IMG_H) == "on_shore"


def test_assess_counts_people_and_uses_manual_water_label():
    dets = [{"cls": "car", "box": CAR, "conf": 0.8}, {"cls": "person", "box": [180, 120, 220, 215], "conf": 0.7}]
    out = assess(dets, 800, IMG_H, "windows")
    assert out["car_detected"] is True
    assert out["water_level"] == "windows" and out["water_level_source"] == "manual_label"
    assert [p["placement"] for p in out["people"]] == ["on_roof"]


def test_assess_rejects_unknown_water_label():
    with pytest.raises(ValueError):
        assess([], 800, IMG_H, "chest-deep")


def test_no_vehicles_means_no_car_detected():
    assert assess([{"cls": "person", "box": [1, 1, 2, 2], "conf": 0.9}], 10, 10, "none")["car_detected"] is False
