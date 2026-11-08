"""Kerrville ground-truth replay (July 4 2025): the pipeline's depth vs the scenario's gauge-driven truth.

Points are synthetic hovers anchored at real critical points (vision/scenes.py). Only points whose truth
comes from the nearest river chain are used (minor-creek crossings use a different model). Drone pose
carries a hover-long GPS/gimbal bias, as in the field.
"""

import json
from datetime import datetime, timezone

import numpy as np
import pytest

pytest.importorskip("osmnx")

from app.config import DATA_DIR  # noqa: E402
from vision.config import vision_config  # noqa: E402
from vision.edges import RoadGeom  # noqa: E402
from vision.measure import PointContext  # noqa: E402
from vision.pipeline import GeoOrigin, PointState, StepInput, snapshot_from_hover  # noqa: E402
from vision.scenes import anchored_scene  # noqa: E402
from vision.segment import lut_from_names  # noqa: E402
from vision.synth import Noise, default_camera, make_frame, oblique_pose, render  # noqa: E402
from vision.water_level import WLParams  # noqa: E402

CFG = vision_config()
TIMES = ("2025-07-04T10:45:00+00:00", "2025-07-04T11:45:00+00:00")   # 05:45 / 06:45 CDT (Kerrville crest)


@pytest.fixture(scope="module")
def replay():
    from sim.region import load_region
    from sim.region_flood import RegionFlood

    region = load_region()
    flood = RegionFlood(region)
    pts = json.loads((DATA_DIR / "region" / "hill_country" / "nodes.json").read_text())["points"]
    return region, flood, pts


def _hover(a, seed):
    cam = default_camera()
    pose = oblique_pose(a.scene)
    rendered = render(a.scene, cam, pose)
    rng = np.random.default_rng(seed)
    base = pose.perturbed(rng, 1.0, 0.5, 0.5)
    ctx = PointContext(a.point_id, a.scene.grid, RoadGeom(a.scene.road, 4.0), cam, lut_from_names())
    state, snap = PointState(), None
    params = WLParams.from_config(CFG["water_level"])
    for k in range(5):
        f = make_frame(a.scene, cam, pose, Noise(flicker_frac=0.03, pose_sigma_m=0.2, pose_sigma_deg=0.1),
                       seed=seed * 10 + k, rendered=rendered, est_base=base)
        snap, state = snapshot_from_hover(ctx, GeoOrigin(a.lon, a.lat), state, f.seg, f.est_pose, [],
                                          StepInput(1.75e9 + 3 * k), params, CFG)
    return snap


def _cases(replay, iso, wet):
    region, flood, pts = replay
    t = datetime.fromisoformat(iso).timestamp()
    out = []
    for p in pts:
        try:
            a = anchored_scene(region, flood, p, t)
        except ValueError:
            continue
        formula = max(0.0, a.scene.wse_m - a.scene.road_min_z()) / 0.0254
        if abs(formula - a.truth_depth_in) <= 1.0 and (a.truth_depth_in > 0) == wet:
            out.append(a)
    return out


@pytest.mark.parametrize("iso", TIMES)
def test_wet_points_measured_depth_brackets_the_replay_truth(replay, iso):
    cases = _cases(replay, iso, wet=True)
    assert len(cases) >= 20
    sample = cases[:: max(1, len(cases) // 8)][:8]
    inside, measured = 0, 0
    for i, a in enumerate(sample):
        snap = _hover(a, i)
        assert snap.water_on_road is True, a.point_id               # never misses water on a flooded road
        if snap.depth_method != "water_edge_dem":
            continue
        measured += 1
        lo, hi = snap.depth_at_road_range_in
        inside += lo <= a.truth_depth_in <= hi
    assert measured >= 6
    assert inside / measured >= 0.85


def test_dry_points_before_the_flood_are_never_reported_flooded(replay):
    cases = _cases(replay, "2025-07-04T06:00:00+00:00", wet=False)[:5]
    assert cases
    for i, a in enumerate(cases):
        snap = _hover(a, 100 + i)
        assert snap.water_on_road is not True, a.point_id
        assert snap.est_depth_in is None
