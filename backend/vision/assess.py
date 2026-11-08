"""Pure rules that turn raw detections into a responder-facing assessment. No model calls here."""

from __future__ import annotations

from typing import Any, Literal

Placement = Literal["on_roof", "in_water", "on_shore", "inside_unknown"]
WaterLevel = Literal["none", "wheels", "doors", "windows", "roof"]

WATER_LEVELS: tuple[str, ...] = ("none", "wheels", "doors", "windows", "roof")
VEHICLE_CLASSES = frozenset({"car", "truck", "bus"})
ROOF_BAND = 0.45          # person's feet within the top 45% of the car box => on the roof
INSIDE_FRACTION = 0.7     # >= 70% of the person box inside the car box => inside the car
SEATED_TOLERANCE = 0.05  # seated person: box centre may sit up to 5% of car height below the roof line
SHORE_BAND = 0.10         # bottom 10% of the frame => assumed shore (heuristic)


def _area(b: list[float]) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _intersection(a: list[float], b: list[float]) -> float:
    return _area([max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])])


def _overlaps_horizontally(a: list[float], b: list[float]) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0])


def _on_roof(person: list[float], car: list[float]) -> bool:
    """Person overlaps the car in x and is standing or sitting on it.

    Standing: feet (box bottom) within the top ROOF_BAND of the car box.
    Seated: legs hang over the windshield, so the feet land lower; instead require the box's vertical
    centre (roughly the hips) at or just below the roof line and the feet inside the car box.
    """
    if not _overlaps_horizontally(person, car):
        return False
    car_top, car_h = car[1], car[3] - car[1]
    feet, centre = person[3], (person[1] + person[3]) / 2
    standing = car_top <= feet <= car_top + ROOF_BAND * car_h
    seated = centre <= car_top + SEATED_TOLERANCE * car_h and car_top < feet <= car[3]
    return standing or seated


def people_placement(person_box: list[float], car_boxes: list[list[float]], img_h: float) -> Placement:
    """Where a detected person is relative to the vehicles in the frame."""
    if any(_on_roof(person_box, car) for car in car_boxes):
        return "on_roof"
    person_area = _area(person_box)
    if person_area > 0 and any(_intersection(person_box, car) / person_area >= INSIDE_FRACTION for car in car_boxes):
        return "inside_unknown"
    # Heuristic only: we can't tell shore from water in a single frame, so a person whose feet are in
    # the bottom band of the image (closest to the camera, usually the bank) is called on_shore.
    if person_box[3] >= (1 - SHORE_BAND) * img_h:
        return "on_shore"
    return "in_water"


def assess(dets: list[dict[str, Any]], img_w: int, img_h: int, manual_label: str) -> dict[str, Any]:
    """car_detected, people (with placement) and the manually labelled water level for one frame.

    img_w is accepted for API symmetry; only img_h feeds the shore heuristic.
    """
    if manual_label not in WATER_LEVELS:
        raise ValueError(f"water level must be one of {WATER_LEVELS}, got {manual_label!r}")
    car_boxes = [d["box"] for d in dets if d["cls"] in VEHICLE_CLASSES]
    people = [
        {"placement": people_placement(d["box"], car_boxes, img_h), "box": d["box"], "conf": d["conf"]}
        for d in dets
        if d["cls"] == "person"
    ]
    return {
        "car_detected": bool(car_boxes),
        "people": people,
        "water_level": manual_label,
        "water_level_source": "manual_label",
    }
