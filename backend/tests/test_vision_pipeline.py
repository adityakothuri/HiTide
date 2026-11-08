"""Snapshot schema (overview 9.5 + plan 8), end-to-end hover pipeline, photo path, and spread (plan 6.4)."""

from datetime import datetime, timezone

import numpy as np
import pytest
from pydantic import ValidationError

from vision.camera import project
from vision.config import vision_config
from vision.detect import Det, Persistence
from vision.edges import RoadGeom
from vision.grid import Seg
from vision.measure import PointContext
from vision.pipeline import GeoOrigin, PointState, StepInput, snapshot_from_hover, snapshot_from_photo
from vision.segment import lut_from_names
from vision.snapshot import VisionSnapshot
from vision.synth import Noise, default_camera, make_frame, oblique_pose, render, valley_scene
from vision.water_level import M_TO_IN, WLParams

CFG = vision_config()
OVERVIEW_FIELDS = ("point_id", "time", "water_on_road", "road_covered_pct", "est_depth_in", "depth_method",
                   "rising", "people_seen", "confidence", "image_url")
T0 = datetime(2025, 7, 4, 10, 45, tzinfo=timezone.utc).timestamp()


# ---------- schema ----------

def _minimal(**kw):
    base = dict(point_id="cp-0001", time=datetime.now(timezone.utc), water_on_road=None, depth_method="none",
                rising=None, people_seen=0, confidence="low")
    return VisionSnapshot(**{**base, **kw})


def test_every_overview_field_is_present_and_unknowns_serialise_as_null():
    out = _minimal().model_dump(mode="json")
    assert set(OVERVIEW_FIELDS) <= set(out)
    assert out["water_on_road"] is None and out["est_depth_in"] is None and out["rising"] is None


@pytest.mark.parametrize("bad", [
    {"est_depth_in": float("nan"), "depth_method": "water_edge_dem"},
    {"est_depth_in": 5.0},                                        # depth without a method
    {"depth_method": "water_edge_dem"},                            # method without a depth
    {"water_on_road": False, "est_depth_in": 8.0, "depth_method": "water_edge_dem"},
    {"people_seen": 2},                                           # disagrees with people[]
    {"image_url": "/static/drone/../../.env"},
    {"image_url": "https://evil.example/x.jpg"},
    {"point_id": "cp/../../x"},
    {"time": datetime(2025, 7, 4, 10, 0)},                        # naive time
    {"water_surface_range_m": (2.0, 1.0)},
    {"rising": True, "trend": "steady"},
    {"unexpected": 1},
])
def test_schema_rejects_inconsistent_or_unsafe_snapshots(bad):
    with pytest.raises(ValidationError):
        _minimal(**bad)


def test_snapshot_is_immutable():
    s = _minimal()
    with pytest.raises(ValidationError):
        s.confidence = "high"


# ---------- end to end: hover over a flooded crossing with a car and a person ----------

@pytest.fixture(scope="module")
def flooded():
    scene = valley_scene(wse_above_bed_m=0.9, bank_slope=0.10)
    cam = default_camera(480, 360)
    pose = oblique_pose(scene)
    return scene, cam, pose, render(scene, cam, pose)


def _car_dets(scene, cam, pose):
    """A car stalled at the road's low point: waterline box from the water plane, person on its roof."""
    uv, _ = project(cam, pose, np.array([[0.0, 0.0, scene.wse_m]]))
    u, v = uv[0]
    car = Det(7, "car", 0.88, (u - 9, v - 5, u + 9, v))
    person = Det(9, "person", 0.61, (u - 2, v - 12, u + 2, v - 4))
    return [car, person]


def _run_hover(scene, cam, pose, rendered, n=6, cases=()):
    ctx = PointContext("cp-test", scene.grid, RoadGeom(scene.road, scene.road_half_width_m), cam, lut_from_names())
    origin = GeoOrigin(-99.14, 30.05)
    params = WLParams.from_config(CFG["water_level"])
    state, snap = PointState(), None
    dets = _car_dets(scene, cam, pose)
    for k in range(n):
        f = make_frame(scene, cam, pose, Noise(flicker_frac=0.02), seed=k, rendered=rendered)
        seg = _paint_objects(f.seg, dets)
        snap, state = snapshot_from_hover(ctx, origin, state, seg, f.est_pose, dets,
                                          StepInput(T0 + 3.0 * k, drone_id="drone-kerrville", cases=cases),
                                          params, CFG)
    return snap


def _paint_objects(seg, dets):
    """The segmenter labels a car/person as a blocker (not water) inside its box."""
    labels, p = seg.labels.copy(), seg.p_water.copy()
    for d in dets:
        x1, y1, x2, y2 = (int(round(c)) for c in d.box)
        labels[max(y1, 0):y2, max(x1, 0):x2] = 20 if d.cls == "car" else 12
        p[max(y1, 0):y2, max(x1, 0):x2] = 0.0
    return Seg(labels, p, seg.low_light)


def test_hover_snapshot_measures_depth_and_finds_the_car_and_person(flooded):
    scene, cam, pose, rendered = flooded
    snap = _run_hover(scene, cam, pose, rendered)
    truth_in = (scene.wse_m - scene.road_min_z()) * M_TO_IN
    assert snap.depth_method == "water_edge_dem" and snap.water_on_road is True
    lo, hi = snap.depth_at_road_range_in
    assert lo <= truth_in <= hi
    assert abs(snap.est_depth_in - truth_in) <= 3.0
    car = next(v for v in snap.vehicles if v.track_id == 7)
    assert car.in_water and car.band_source == "water_surface"
    assert abs(car.depth_at_vehicle_in - truth_in) <= 6.0
    assert snap.people[0].situation == "on_vehicle" and snap.people_seen == 1
    top = snap.alerts[0]
    assert top.priority == "critical" and top.kind == "person_on_vehicle" and top.boat_required  # ~35 in > 24
    assert set(OVERVIEW_FIELDS) <= set(snap.model_dump())


def test_detections_must_persist_before_they_reach_the_snapshot(flooded):
    scene, cam, pose, rendered = flooded
    snap = _run_hover(scene, cam, pose, rendered, n=4)
    assert snap.vehicles == [] and snap.people == [] and snap.alerts == []


def test_car_in_water_near_an_open_case_joins_it(flooded):
    scene, cam, pose, rendered = flooded
    cases = ({"id": "case-001", "state": "drone_en_route", "lat": 30.05, "lon": -99.14},)
    snap = _run_hover(scene, cam, pose, rendered, cases=cases)
    car = next(v for v in snap.vehicles if v.track_id == 7)
    assert car.matched_case_id == "case-001"
    # the car is occupied: ONE critical alert (person_on_vehicle) carries the case, no duplicate for the car
    linked = [a for a in snap.alerts if a.case_id == "case-001"]
    assert len(linked) == 1 and linked[0].kind == "person_on_vehicle"


def test_dry_crossing_reports_no_depth_and_no_band():
    scene = valley_scene(wse_above_bed_m=-0.5)                    # river below its bed: no water at all
    cam = default_camera()
    pose = oblique_pose(scene)
    ctx = PointContext("cp-dry", scene.grid, RoadGeom(scene.road, 4.0), cam, lut_from_names())
    f = make_frame(scene, cam, pose)
    snap, _ = snapshot_from_hover(ctx, GeoOrigin(-99.1, 30.0), PointState(), f.seg, pose, [],
                                  StepInput(T0), WLParams.from_config(CFG["water_level"]), CFG)
    assert snap.water_on_road is False and snap.est_depth_in is None and snap.depth_band is None
    assert snap.depth_method == "none" and snap.confidence == "low"


# ---------- photo path (no pose) ----------

def _photo_seg(water_top):
    labels = np.full((200, 300), 13, np.int16)
    p = np.zeros((200, 300), np.float32)
    p[water_top:] = 0.9
    return Seg(labels, p)


def test_photo_with_a_car_in_water_is_wet_but_never_guesses_depth_from_the_car():
    car = Det(0, "car", 0.9, (100.0, 100.0, 200.0, 121.0))       # half hidden: the shape would say windows
    wet = snapshot_from_photo("photo-1", _photo_seg(80), [car], StepInput(T0, source="photo"), CFG)
    assert wet.water_on_road is True and wet.depth_method == "none" and wet.est_depth_in is None
    assert wet.depth_band is None and all(v.band is None for v in wet.vehicles)
    assert any(a.boat_required for a in wet.alerts)              # unknown depth -> boat, never truck
    dry = snapshot_from_photo("photo-2", _photo_seg(200), [], StepInput(T0, source="photo"), CFG)
    assert dry.water_on_road is None and dry.depth_method == "none"


# ---------- spread (plan 6.4) on the real Hill Country region ----------

@pytest.fixture(scope="module")
def region():
    from sim.region import load_region

    return load_region("hill_country")


def test_spread_matches_the_region_flood_formula_and_is_never_confirmed(region, monkeypatch):
    from sim.region_flood import RegionFlood
    from vision.spread import nearest_chain, spread

    ch = region.chains["Guadalupe River"] if "Guadalupe River" in region.chains else next(iter(region.chains.values()))
    k = len(ch.s_m) // 2
    lon, lat = float(ch.lon[k]), float(ch.lat[k])
    ref = nearest_chain(region, lon, lat)
    rise = 4.0
    out = spread(region, lon, lat, ref.z_ref_m + rise, reach_m=1e9)
    assert out and all(s.status == "likely_flooded" and s.source == "drone_wse_spread" for s in out)

    flood = RegionFlood.__new__(RegionFlood)
    flood.region = region
    monkeypatch.setattr(flood, "chain_rise", lambda name, t, belief: np.full(region.chains[name].s_m.shape,
                        rise if name == ref.chain else np.nan), raising=False)
    expected = flood._depths(0.0, belief=True)
    got = {s.edge_id: s.est_depth_in for s in out}
    for i in np.nonzero(expected > 0)[0]:
        assert got[region.edge_ids[i]] == pytest.approx(expected[i], abs=0.1)
    assert len(got) == int((expected > 0).sum())


def test_spread_is_limited_by_reach_and_needs_a_rise(region):
    from vision.spread import nearest_chain, spread

    ch = next(iter(region.chains.values()))
    k = len(ch.s_m) // 2
    lon, lat = float(ch.lon[k]), float(ch.lat[k])
    z = nearest_chain(region, lon, lat).z_ref_m
    assert spread(region, lon, lat, z - 0.5) == []
    assert len(spread(region, lon, lat, z + 4, reach_m=200)) <= len(spread(region, lon, lat, z + 4, reach_m=5000))
