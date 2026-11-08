"""Critical-point priority (overview.md 8.4) and the worked example (8.7)."""

from __future__ import annotations

import math

import pytest

from critical.score import NodeUse, PointInput, priority, rank, uncertainty


def _use(node, hh, kind="unavoidable", older=0.0, one_story=0.0, cars=0.0):
    return NodeUse(node_id=node, households=hh, kind=kind, older_share=older,
                   one_story_share=one_story, cars_home_share=cars)


def test_uncertainty_is_scaled_bernoulli_variance():
    assert uncertainty(0.5) == pytest.approx(1.0)
    assert uncertainty(0.0) == 0.0 and uncertainty(1.0) == 0.0
    assert uncertainty(0.95) == pytest.approx(0.19)


def test_breakdown_multiplies_the_five_factors():
    b = priority(PointInput("X", p=0.5, uses=(_use("v", 40, older=0.5),), urgent=True))
    assert b.dependency == pytest.approx(40.0)
    assert b.vulnerability == pytest.approx(1.25)
    assert b.p_weight == pytest.approx(1.0)
    assert b.uncertainty == pytest.approx(1.0)
    assert b.urgency == pytest.approx(1.5)
    assert b.priority == pytest.approx(40 * 1.25 * 1.0 * 1.0 * 1.5)


def test_optional_use_counts_less_than_unavoidable():
    hard = priority(PointInput("A", 0.5, (_use("n", 10),), False)).priority
    soft = priority(PointInput("B", 0.5, (_use("n", 10, kind="optional"),), False)).priority
    assert soft == pytest.approx(0.3 * hard)


def test_known_point_scores_zero_never_wastes_a_flight():
    assert priority(PointInput("K", 1.0, (_use("n", 500),), True)).priority == 0.0
    assert priority(PointInput("K", 0.0, (_use("n", 500),), True)).priority == 0.0


def test_vulnerability_is_household_weighted():
    b = priority(PointInput("X", 0.5, (_use("a", 30, older=1.0), _use("b", 10, older=0.0)), False))
    assert b.vulnerability == pytest.approx(1 + 0.5 * 0.75)


def test_value_peaks_on_the_likely_flooded_side():
    """(0.5+p)*4p(1-p) peaks at p=(1+sqrt 7)/6 ~ 0.61: missing a flood costs more than missing a dry road."""
    best = max((i / 1000 for i in range(1001)), key=lambda p: (0.5 + p) * uncertainty(p))
    assert best == pytest.approx((1 + math.sqrt(7)) / 6, abs=1e-3)


def test_worked_example_ranks_x1_first_and_sensor_point_last():
    x1 = PointInput("X1", 0.5, (_use("village", 40), _use("farm", 1)), False)
    x2 = PointInput("X2", 0.6, (_use("subdivision", 25, kind="optional"),), False)
    x3 = PointInput("X3", 0.95, (_use("subdivision", 25, kind="optional"),), False)
    ranked = rank([x3, x2, x1])
    assert [r.point_id for r in ranked] == ["X1", "X2", "X3"]
    assert ranked[0].uncertainty == pytest.approx(1.0)
    assert ranked[2].uncertainty == pytest.approx(0.19)


def test_point_with_no_dependents_is_dropped_from_ranking():
    lonely = PointInput("ridge", 0.5, (), False)
    assert rank([lonely]) == []


def test_rejects_probability_outside_unit_interval():
    with pytest.raises(ValueError):
        priority(PointInput("bad", 1.2, (_use("n", 1),), False))
