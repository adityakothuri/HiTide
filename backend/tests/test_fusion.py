"""Segment p_flooded from evidence (overview.md 6.3) with drone evidence decay (6.4)."""

from __future__ import annotations

import pytest

from fusion.segment_status import DroneObs, Signals, p_flooded, status


def test_priors_inside_and_outside_warning():
    assert p_flooded(Signals(floodable=True, in_warning=False)) == pytest.approx(0.02)
    assert p_flooded(Signals(floodable=True, in_warning=True)) == pytest.approx(0.30)
    assert p_flooded(Signals(floodable=False, in_warning=True)) == pytest.approx(0.02)


def test_supporting_evidence_adds_up():
    s = Signals(floodable=True, in_warning=True, gauge_rising=True, model_above_road=True)
    assert p_flooded(s) == pytest.approx(0.60)


def test_indirect_evidence_alone_never_confirms():
    s = Signals(True, True, gauge_rising=True, model_above_road=True, heavy_rain=True, driver_signals=True)
    assert p_flooded(s) == pytest.approx(0.85)
    assert status(p_flooded(s)) == "likely_flooded"


def test_direct_evidence_overrides():
    assert p_flooded(Signals(True, False, closure=True)) == pytest.approx(0.95)
    assert p_flooded(Signals(True, True, drone=DroneObs(wet=True, age_s=0))) == pytest.approx(0.95)
    assert p_flooded(Signals(True, True, gauge_rising=True, drone=DroneObs(wet=False, age_s=0))) == pytest.approx(0.10)


def test_confirmed_flooded_does_not_decay():
    assert p_flooded(Signals(True, True, drone=DroneObs(wet=True, age_s=10_000), gauges_rising=True)) == pytest.approx(0.95)


def test_dry_snapshot_drifts_back_to_prior_faster_while_rising():
    rising = Signals(True, True, gauges_rising=True, drone=DroneObs(wet=False, age_s=1800))
    steady = Signals(True, True, gauges_rising=False, drone=DroneObs(wet=False, age_s=1800))
    assert p_flooded(rising) == pytest.approx(0.5 * 0.10 + 0.5 * 0.30)  # one 30-min half-life
    assert p_flooded(steady) < p_flooded(rising)


@pytest.mark.parametrize("p,expected", [(0.02, "open"), (0.14, "open"), (0.3, "unknown"), (0.6, "likely_flooded"),
                                        (0.95, "confirmed_flooded")])
def test_status_bands(p, expected):
    assert status(p) == expected
