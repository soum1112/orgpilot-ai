"""Targets are never invented; cross-dataset comparison is refused unless compatible."""
import math

import pytest

from kpi_engine import TARGETS, TargetSpec
from .conftest import emp, emp_syn, mkt, po

M, P, E, S = "marketing_daily", "procurement_po", "employee_kpi_public", "employee_kpi_synthetic"


# ---------- targets
def test_no_target_defined_by_default_and_none_registered(engine):
    r = engine(marketing_daily=mkt([dict()])).compute("marketing.roas", M)
    assert r.target["status"] == "no_target_defined" and r.target["value"] is None and r.target["evidence_type"] == "target"
    assert TARGETS == {}  # no source document states a numeric target for any registered KPI


def test_target_requires_a_source_and_finite_value():
    for bad in (dict(value=1.0, source=""), dict(value=1.0, source="   "), dict(value=float("nan"), source="x"),
                dict(value=math.inf, source="x")):
        with pytest.raises(ValueError):
            TargetSpec(**bad)
    with pytest.raises(ValueError):
        TargetSpec(value=1.0, source="x", direction="sideways")


def test_higher_is_better_target_met_and_not_met(engine):
    e = engine(marketing_daily=mkt([dict(mark_spent=100.0, revenue=150.0)]))
    met = e.compute("marketing.roas", M, target=TargetSpec(1.2, "Board plan 2021"))
    miss = e.compute("marketing.roas", M, target=TargetSpec(2.0, "Board plan 2021"))
    assert met.target["status"] == "met" and miss.target["status"] == "not_met"
    assert miss.target["gap_abs"] == pytest.approx(-0.5) and miss.target["gap_pct"] == pytest.approx(-25.0)
    assert miss.target["source"] == "Board plan 2021"
    assert miss.evidence_type.value == "observed" and miss.target["evidence_type"] == "target"


def test_lower_is_better_uses_registry_direction(engine):
    e = engine(marketing_daily=mkt([dict(mark_spent=300.0, orders=3)]))  # CPO 100
    assert e.compute("marketing.cost_per_order", M, target=TargetSpec(120, "src")).target["status"] == "met"
    assert e.compute("marketing.cost_per_order", M, target=TargetSpec(80, "src")).target["status"] == "not_met"


def test_direction_override_and_zero_target(engine):
    e = engine(marketing_daily=mkt([dict(mark_spent=300.0, orders=3)]))
    r = e.compute("marketing.cost_per_order", M, target=TargetSpec(120, "src", direction="higher_is_better"))
    assert r.target["status"] == "not_met"
    z = e.compute("marketing.cost_per_order", M, target=TargetSpec(0, "src"))
    assert z.target["gap_pct"] is None and z.target["status"] == "not_met"


def test_target_not_evaluable_when_value_is_none(engine):
    r = engine(marketing_daily=mkt([dict(mark_spent=0.0)])).compute("marketing.roas", M, target=TargetSpec(1.0, "src"))
    assert r.value is None and r.target["status"] == "not_evaluable" and r.target["gap_abs"] is None


def test_grouped_results_each_carry_target_evaluation(engine):
    e = engine(marketing_daily=mkt([dict(campaign_name="a", mark_spent=100.0, revenue=200.0),
                                    dict(campaign_name="b", c_date="2021-02-02", mark_spent=100.0, revenue=50.0)]))
    res = e.compute_grouped("marketing.roas", M, "campaign", target=TargetSpec(1.0, "src"))
    assert {r.group["campaign"]: r.target["status"] for r in res} == {"a": "met", "b": "not_met"}


# ---------- comparability
@pytest.fixture
def two_employee_sets(engine):
    return engine(employee_kpi_public=emp([dict(month="2024-01"), dict(month="2024-03", employee_id="E2")]),
                  employee_kpi_synthetic=emp_syn([dict(month="2026-01"), dict(month="2026-02", employee_id="E2")]))


def test_public_vs_synthetic_employee_kpis_are_not_comparable(two_employee_sets):
    c = two_employee_sets.check_comparability(E, S, "performance.avg_performance_score")
    text = " | ".join(c["reasons"])
    assert c["comparable"] is False
    for needle in ("different data sources", "different populations", "non-overlapping periods", "circular"):
        assert needle in text


def test_dataset_is_comparable_with_itself(two_employee_sets):
    assert two_employee_sets.check_comparability(E, E, "performance.avg_performance_score")["comparable"] is True


def test_marketing_vs_procurement_not_comparable(engine):
    e = engine(marketing_daily=mkt([dict()]), procurement_po=po([dict()]))
    c = e.check_comparability(M, P, "marketing.roas")
    assert not c["comparable"] and any("not defined for dataset 'procurement_po'" in r for r in c["reasons"])


def test_unloaded_dataset_cannot_be_verified(engine):
    c = engine(marketing_daily=mkt([dict()])).check_comparability(M, P)
    assert not c["comparable"]
