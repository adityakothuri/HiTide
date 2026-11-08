"""Water surface, depth and confidence: stress tests against exact synthetic ground truth.

Drone vision plan sections 6 and 12; overview 6.3 / 9.4 / 9.7. Tolerances are the measured behaviour
(see vault/Experiments/2026-11-08 Drone vision accuracy.md), not wishes.
"""

from dataclasses import replace

import numpy as np
import pytest

from vision.config import vision_config
from vision.edges import EdgeSet, RoadGeom, extract_edges
from vision.grid import GROUND, INVALID, WATER, CellObs, GroundGrid
from vision.measure import INFERRED_REASON, PointContext, measure
from vision.segment import lut_from_names
from vision.synth import Noise, default_camera, make_frame, oblique_pose, render, valley_scene
from vision.water_level import (
    M_TO_IN, WSE, WLParams, depth_at_road, estimate_wse, levelset_wse, road_band, road_state, score_confidence,
)

CFG = vision_config()
EXACT = WLParams.from_config(CFG["water_level"], dem_error_m=0.0)


def _ctx(scene, cam):
    return PointContext("t", scene.grid, RoadGeom(scene.road, scene.road_half_width_m), cam, lut_from_names())


@pytest.fixture(scope="module")
def valley():
    scene = valley_scene(wse_above_bed_m=0.8, bank_slope=0.12)
    cam = default_camera()
    pose = oblique_pose(scene)
    return scene, cam, pose, render(scene, cam, pose)


def _hover(scene, cam, pose, rendered, noise=Noise(), n=5, seed=0, est_base=None):
    return [
        (f.seg, f.est_pose)
        for f in (make_frame(scene, cam, pose, noise, seed=seed * 100 + k, rendered=rendered, est_base=est_base)
                  for k in range(n))
    ]


# ---------- end to end on synthetic truth ----------

@pytest.mark.parametrize("above_bed", [0.3, 0.8, 1.5])
def test_noise_free_recovers_water_surface_and_road_depth(above_bed):
    scene = valley_scene(wse_above_bed_m=above_bed)
    cam = default_camera()
    pose = oblique_pose(scene)
    m = measure(_ctx(scene, cam), _hover(scene, cam, pose, render(scene, cam, pose), n=1), EXACT, CFG)
    truth_depth_in = (scene.wse_m - scene.road_min_z()) * M_TO_IN
    assert abs(m.wse.wse_m - scene.wse_m) <= 0.01
    assert abs(m.depth.depth_in - truth_depth_in) <= 0.5
    assert m.wse.sides == 2 and m.water_on_road is True
    assert m.band == road_band(truth_depth_in, CFG["road_band_in"])
    assert abs(m.levelset[0] - scene.wse_m) <= 0.03
    assert "estimators agree" in m.reasons


def test_reported_range_is_honest_under_hover_long_pose_bias_and_mask_bias(valley):
    """Coverage: the truth must fall inside the reported range in >= 90% of trials (plan 4)."""
    scene, cam, pose, rendered = valley
    errs, covered = [], 0
    for i in range(40):
        rng = np.random.default_rng(i)
        base = pose.perturbed(rng, 1.0, 0.5, 0.5)          # GPS/gimbal bias held for the whole hover
        bpx = int(np.clip(round(rng.normal(0, 2.0)), -5, 5))  # systematic segmentation boundary bias
        noise = Noise(boundary_px=bpx, flicker_frac=0.05, pose_sigma_m=0.2, pose_sigma_deg=0.1, pose_sigma_z_m=0.1)
        m = measure(_ctx(scene, cam), _hover(scene, cam, pose, rendered, noise, seed=i, est_base=base), EXACT, CFG)
        assert m.wse is not None
        errs.append(abs(m.wse.wse_m - scene.wse_m))
        covered += m.wse.lo_m <= scene.wse_m <= m.wse.hi_m
    assert covered / 40 >= 0.90
    assert np.percentile(errs, 95) <= 0.30
    assert np.median(errs) <= 0.10


def test_tree_over_the_water_edge_is_not_used(valley):
    scene, cam, pose, _ = valley
    bank_x = 3.0 + 0.8 / 0.12                               # where the east bank meets the water
    treed = replace(scene, trees=((bank_x, 20.0, 6.0),))
    m = measure(_ctx(treed, cam), _hover(treed, cam, pose, render(treed, cam, pose), n=1), EXACT, CFG)
    # edges just outside the canopy are real water/ground contacts; none may come from under the canopy
    under_canopy = np.hypot(m.edges.xy[:, 0] - bank_x, m.edges.xy[:, 1] - 20.0) < 6.0
    assert not under_canopy.any()
    assert abs(m.wse.wse_m - scene.wse_m) <= 0.01


def test_ten_percent_dem_outliers_barely_move_the_estimate(valley):
    scene, cam, pose, rendered = valley
    rng = np.random.default_rng(3)
    z = scene.grid.z.copy()
    bad = rng.random(z.shape) < 0.10
    z[bad] += rng.choice([-1.0, 1.0], bad.sum())
    noisy_dem = replace(scene, grid=GroundGrid(scene.grid.x0, scene.grid.y0, scene.grid.res, z))
    m = measure(_ctx(noisy_dem, cam), _hover(scene, cam, pose, rendered, n=1), EXACT, CFG)
    assert abs(m.wse.wse_m - scene.wse_m) <= 0.03


def test_steep_banks_widen_the_range_and_say_so():
    gentle, steep = valley_scene(bank_slope=0.06), valley_scene(bank_slope=0.40)
    cam = default_camera()
    out = {}
    for name, sc in (("gentle", gentle), ("steep", steep)):
        pose = oblique_pose(sc)
        m = measure(_ctx(sc, cam), _hover(sc, cam, pose, render(sc, cam, pose), n=1), WLParams.from_config(CFG["water_level"]), CFG)
        out[name] = m
    assert (out["steep"].wse.hi_m - out["steep"].wse.wse_m) > (out["gentle"].wse.hi_m - out["gentle"].wse.wse_m)
    assert "steep bank" in out["steep"].reasons
    assert out["steep"].confidence == "low"


def test_drift_during_the_hover_is_absorbed_by_the_ground_grid_vote(valley):
    scene, cam, pose, _ = valley
    frames = []
    for k, dx in enumerate((-3.0, -1.5, 0.0, 1.5, 3.0)):     # 6 m of drift across the vote window
        p = replace(pose, x=pose.x + dx, heading_deg=pose.heading_deg + 0.8 * k)
        f = make_frame(scene, cam, p, seed=k)
        frames.append((f.seg, p))
    m = measure(_ctx(scene, cam), frames, EXACT, CFG)
    assert abs(m.wse.wse_m - scene.wse_m) <= 0.01


def test_road_hidden_but_water_level_above_its_low_point_is_inferred_wet_with_reason(valley):
    scene, cam, pose, rendered = valley
    ctx = _ctx(scene, cam)
    seg, p = _hover(scene, cam, pose, rendered, n=1)[0]
    from vision.grid import label_cells

    obs = label_cells(scene.grid, seg, cam, p, ctx.lut)
    # hide the road everywhere (tree canopy) so the mask can't see it
    hidden = CellObs(np.where(np.abs(scene.grid.xy()[1]) <= 5, INVALID, obs.group).astype(np.int8), obs.p_water)
    rs = road_state(hidden, scene.grid, ctx.road, CFG["road"])
    assert rs.water_on_road is None
    m = measure(ctx, [(seg, p)], EXACT, CFG)
    assert m.water_on_road is True and m.road.water_on_road is True  # visible here: control
    assert INFERRED_REASON not in m.reasons


# ---------- unit: robust estimator ----------

def _edges(z, side=None, slope=0.1):
    z = np.asarray(z, dtype=float)
    side = np.where(np.arange(len(z)) % 2 == 0, 1, -1) if side is None else np.asarray(side)
    return EdgeSet(np.zeros((len(z), 2)), z, side, np.full(len(z), slope))


def test_outliers_are_rejected_by_the_mad_rule():
    rng = np.random.default_rng(0)
    z = 100.0 + rng.normal(0, 0.01, 200)
    z[:20] += rng.choice([-2.0, 3.0], 20)                    # 10% gross errors
    est = estimate_wse(_edges(z), EXACT)
    assert abs(est.wse_m - 100.0) <= 0.01
    assert est.n_inliers <= 185


def test_mad_zero_uses_the_floor_and_does_not_crash():
    est = estimate_wse(_edges([50.0] * 40), EXACT)
    assert est.wse_m == 50.0
    assert est.sigma_m >= EXACT.mad_floor_m * 1.4826 - 1e-9


def test_too_few_edge_points_gives_none_not_a_guess():
    assert estimate_wse(_edges([10.0] * 29), EXACT) is None
    level, reasons = score_confidence(None, EXACT)
    assert level == "low" and "too few edge points" in reasons


def test_one_side_only_widens_the_range_by_the_configured_factor():
    # no pose error here: one side also loses the two-bank cancellation of pose error, tested separately
    params = replace(EXACT, pose_sigma_m=0.0, pose_sigma_deg=0.0)
    z = 100.0 + np.random.default_rng(1).normal(0, 0.02, 60)
    two = estimate_wse(_edges(z), params)
    one = estimate_wse(_edges(z, side=np.ones(60)), params)
    assert one.sides == 1 and "one side only" in one.reasons
    assert (one.hi_m - one.wse_m) == pytest.approx(params.one_side_widen * (two.hi_m - two.wse_m), rel=1e-6)


def test_one_side_loses_the_two_bank_cancellation_of_pose_error():
    z = 100.0 + np.random.default_rng(1).normal(0, 0.02, 60)
    two = estimate_wse(_edges(z), EXACT, slant_m=80.0)
    one = estimate_wse(_edges(z, side=np.ones(60)), EXACT, slant_m=80.0)
    assert (one.hi_m - one.wse_m) > EXACT.one_side_widen * (two.hi_m - two.wse_m)


def test_levelset_finds_the_split_level():
    z = np.linspace(0, 2, 101)[None, :].repeat(3, axis=0)
    group = np.where(z < 1.2, WATER, GROUND).astype(np.int8)
    ls = levelset_wse(CellObs(group, np.where(group == WATER, 0.9, 0.1)), GroundGrid(0, 0, 1, z))
    assert ls[0] == pytest.approx(1.2, abs=0.02)


def test_levelset_needs_both_water_and_ground():
    z = np.zeros((3, 3))
    assert levelset_wse(CellObs(np.full((3, 3), GROUND, np.int8), np.zeros((3, 3))), GroundGrid(0, 0, 1, z)) is None


# ---------- unit: road state, depth, bands, confidence ----------

def _road_grid():
    z = np.zeros((21, 41))
    return GroundGrid(-10, -5, 0.5, z), RoadGeom(np.array([[-9.0, 0.0], [9.0, 0.0]]), 2.0)


def test_road_fully_visible_and_dry_is_false_but_mostly_hidden_and_dry_is_unknown():
    grid, road = _road_grid()
    dry = CellObs(np.full(grid.shape, GROUND, np.int8), np.zeros(grid.shape))
    assert road_state(dry, grid, road, CFG["road"]).water_on_road is False
    hidden = CellObs(np.where(np.arange(41)[None, :] < 30, INVALID, GROUND).repeat(21, 0).astype(np.int8),
                     np.zeros(grid.shape))
    assert road_state(hidden, grid, road, CFG["road"]).water_on_road is None


def test_small_wet_patch_on_a_long_road_is_still_water_on_road():
    grid, road = _road_grid()
    g = np.full(grid.shape, GROUND, np.int8)
    g[8:13, 18:24] = WATER                                   # 2.5 m x 3 m = 7.5 m2 on a 18 m road
    rs = road_state(CellObs(g, np.where(g == WATER, 0.9, 0.1)), grid, road, CFG["road"])
    assert rs.water_on_road is True and rs.covered_pct < 20


def test_surface_clearly_below_road_is_no_depth_and_contradiction_drops_confidence():
    est = WSE(99.0, 0.05, 98.9, 99.1, 50, 50, 2, 0.1, ("two sides",))
    assert depth_at_road(est, 100.0) is None
    level, reasons = score_confidence(est, EXACT, contradiction=True)
    assert level == "low" and "edge/road disagree" in reasons


def test_depth_range_is_clamped_at_zero_but_keeps_upper_bound():
    est = WSE(100.02, 0.05, 99.92, 100.12, 50, 50, 2, 0.1, ())
    d = depth_at_road(est, 100.0)
    assert d.lo_in == 0.0 and d.hi_in == pytest.approx(0.12 * M_TO_IN)


@pytest.mark.parametrize("depth,band", [
    (0.0, "shallow"), (2.9, "shallow"), (3.0, "caution"), (5.9, "caution"), (6.0, "dangerous"),
    (11.9, "dangerous"), (12.0, "vehicles_float"), (23.9, "vehicles_float"), (24.0, "boat_only"), (80, "boat_only"),
])
def test_road_bands_follow_weights_yaml(depth, band):
    assert road_band(depth, CFG["road_band_in"]) == band


def test_no_band_is_ever_called_open_or_safe():
    names = {road_band(d, CFG["road_band_in"]) for d in np.linspace(0, 100, 501)}
    assert not names & {"open", "safe", "clear"}


def test_low_light_caps_confidence_at_medium():
    est = WSE(100.0, 0.01, 99.98, 100.02, 80, 80, 2, 0.05, ("two sides",))
    agree = (100.0, 0.01)
    assert score_confidence(est, EXACT, levelset=agree)[0] == "high"
    assert score_confidence(est, EXACT)[0] == "medium"                     # no cross-check, no "high"
    level, reasons = score_confidence(est, EXACT, levelset=agree, low_light=True)
    assert level == "medium" and "low light" in reasons


def test_estimator_disagreement_drops_to_low():
    est = WSE(100.0, 0.01, 99.98, 100.02, 80, 80, 2, 0.05, ("two sides",))
    level, reasons = score_confidence(est, EXACT, levelset=(100.30, 0.02))
    assert level == "low" and "estimators disagree" in reasons


def test_empty_grid_yields_no_edges():
    grid, road = _road_grid()
    obs = CellObs(np.full(grid.shape, GROUND, np.int8), np.zeros(grid.shape))
    assert len(extract_edges(obs, grid, road)) == 0
