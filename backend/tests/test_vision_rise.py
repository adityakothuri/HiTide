"""Rise rate (drone vision plan 6.3): false-alarm and detection rates on noisy synthetic series."""

from collections import Counter

import numpy as np

from vision.rise import RiseTracker

SIGMA_M = 0.03          # per-frame water-surface noise
FPS = 3.3               # one processed frame every 0.3 s


def _trend(rate_in_hr: float, seed: int, *, hover_s: float = 25.0, revisits: int = 1, gap_s: float = 600.0,
           bias_sigma_m: float = 0.10):
    """Each hover gets its OWN pose bias (GPS/attitude error isn't shared between flights)."""
    rng = np.random.default_rng(seed)
    r = RiseTracker()
    for v in range(revisits):
        bias = rng.normal(0, bias_sigma_m)
        for t in v * gap_s + np.arange(0, hover_s, 1 / FPS):
            wse = 100 + bias + rate_in_hr * 0.0254 / 3600 * t + rng.normal(0, SIGMA_M)
            r = r.add("cp-1", float(t), wse, bias_sigma_m)
    return r.trend("cp-1")


def _counts(rate, n=100, **kw):
    return Counter(_trend(rate, s, **kw).trend for s in range(n))


def test_still_water_over_one_hover_rarely_reads_rising():
    c = _counts(0.0)
    assert c["rising"] <= 5


def test_fast_rise_in_one_hover_is_rising_or_unknown_never_falling_or_steady():
    c = _counts(200.0)
    assert c["rising"] >= 40
    assert c["falling"] == 0 and c["steady"] == 0


def test_still_water_across_revisits_with_fresh_bias_per_hover_rarely_reads_rising_or_falling():
    """Regression: a per-hover bias of 10 cm over 10 min must not read as a ~24 in/hr trend."""
    c = _counts(0.0, revisits=3)
    assert c["rising"] <= 5 and c["falling"] <= 5


def test_fast_rise_is_caught_across_revisits_despite_per_hover_bias():
    assert _counts(60.0, revisits=3)["rising"] >= 90         # 20 in over 20 min vs 4 in of bias per hover


def test_slow_rise_with_gps_grade_pose_is_honestly_unknown_not_steady():
    c = _counts(6.0, revisits=3)                             # 2 in over 20 min is below a 4 in hover bias
    assert c["steady"] <= 10 and c["falling"] <= 5             # a 95% interval: ~2.5% per tail


def test_slow_rise_is_caught_with_rtk_grade_pose():
    assert _counts(6.0, revisits=3, bias_sigma_m=0.005)["rising"] >= 90


def test_unknown_maps_to_null_rising_and_rate_has_units():
    t = RiseTracker().add("a", 0, 1.0).trend("a")
    assert t.trend == "unknown" and t.rising is None and t.rate_in_per_hr is None
    t = _trend(60.0, 0, revisits=3)
    assert t.rising is True and 30 < t.rate_in_per_hr < 90


def test_nan_estimates_are_ignored_not_propagated():
    r = RiseTracker()
    for k in range(10):
        r = r.add("a", float(k), float("nan") if k == 3 else 1.0)
    t = r.trend("a")
    assert len(r.series["a"]) == 9 and all(v is None or np.isfinite(v) for v in (t.lo_in_per_hr, t.hi_in_per_hr))


def test_add_returns_a_new_tracker_and_old_points_age_out():
    r0 = RiseTracker(max_age_s=100)
    r1 = r0.add("a", 0, 1.0)
    r2 = r1.add("a", 500, 1.0)
    assert "a" not in r0.series and len(r1.series["a"]) == 1 and len(r2.series["a"]) == 1


def test_unknown_trend_never_reports_a_noise_rate():
    for seed in range(30):
        t = _trend(0.0, seed, hover_s=12.0)
        if t.trend == "unknown":
            assert t.rate_in_per_hr is None


def test_a_quick_revisit_with_a_new_bias_is_not_read_as_a_rise():
    """Audit regression: 15 s hover, 45 s gap, +10 cm bias on still water read 'rising 206 in/hr'."""
    rng = np.random.default_rng(0)
    r = RiseTracker()
    for visit, (start, bias) in enumerate([(0.0, 0.0), (60.0, 0.10)]):
        for t in start + np.arange(0, 15, 1 / FPS):
            r = r.add("cp-1", float(t), 100 + bias + rng.normal(0, 0.005), 0.10, visit=visit)
    assert r.trend("cp-1").trend != "rising"
