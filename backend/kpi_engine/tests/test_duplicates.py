"""Exact duplicates are removed; conflicting duplicate keys follow an explicit, reported policy."""
import pytest

from .conftest import emp, emp_syn, mkt, po

M, P, E, S = "marketing_daily", "procurement_po", "employee_kpi_public", "employee_kpi_synthetic"


def test_exact_duplicate_rows_removed_once_and_reported(engine):
    base = [dict(c_date="2021-02-01", mark_spent=100.0, revenue=200.0), dict(c_date="2021-02-02", mark_spent=50.0, revenue=50.0)]
    clean = engine(marketing_daily=mkt(base)).compute("marketing.roas", M)
    dup = engine(marketing_daily=mkt(base + [base[0]])).compute("marketing.roas", M)
    assert dup.value == clean.value and dup.n_rows_input == 2
    assert any("1 exact duplicate rows removed" in w for w in dup.warnings)


def test_duplicate_po_with_conflicting_values_excluded_by_default(engine):
    rows = [dict(PO_ID="1", Quantity=100, Negotiated_Price=9.0), dict(PO_ID="1", Quantity=100, Negotiated_Price=5.0),
            dict(PO_ID="2", Quantity=100, Negotiated_Price=9.0)]
    r = engine(procurement_po=po(rows)).compute("procurement.savings_pct", P)
    assert r.n_rows_input == 1 and r.value == pytest.approx(10.0)
    assert any("multiple non-identical rows" in w and "excluded" in w for w in r.warnings)


def test_conflict_policy_keep_counts_all_rows(engine):
    rows = [dict(PO_ID="1", Negotiated_Price=9.0), dict(PO_ID="1", Negotiated_Price=5.0)]
    r = engine(procurement_po=po(rows)).compute("procurement.savings_pct", P, conflict_policy="keep")
    assert r.n_rows_input == 2 and r.value == pytest.approx(30.0)  # (1 + 5) / 20 * 100 on qty-weighted values


def test_invalid_conflict_policy_rejected(engine):
    with pytest.raises(ValueError):
        engine(procurement_po=po([dict()])).compute("procurement.savings_pct", P, conflict_policy="average")


def test_marketing_same_day_same_campaign_conflict_excluded(engine):
    rows = [dict(c_date="2021-02-01", campaign_name="a", revenue=100.0), dict(c_date="2021-02-01", campaign_name="A ", revenue=999.0),
            dict(c_date="2021-02-02", campaign_name="a", revenue=100.0)]
    r = engine(marketing_daily=mkt(rows)).compute("marketing.roas", M)
    assert r.n_rows_input == 1  # both conflicting rows dropped (names normalise to the same key)


def test_public_employee_record_level_conflicts_kept_but_reported(engine):
    rows = [dict(employee_id="A", month="2024-01", department="HR", performance_score=10.0),
            dict(employee_id="A", month="2024-01", department="IT", performance_score=20.0)]
    r = engine(employee_kpi_public=emp(rows)).compute("performance.avg_performance_score", E)
    assert r.n_rows_input == 2 and r.value == pytest.approx(15.0)
    assert any("kept (record-level data)" in w for w in r.warnings)


def test_synthetic_employee_month_is_a_primary_key_conflicts_excluded(engine):
    rows = [dict(employee_id="A", month="2026-01", performance_score=10.0),
            dict(employee_id="A", month="2026-01", performance_score=30.0),
            dict(employee_id="B", month="2026-01", performance_score=20.0)]
    r = engine(employee_kpi_synthetic=emp_syn(rows)).compute("performance.avg_performance_score", S)
    assert r.n_rows_input == 1 and r.value == pytest.approx(20.0)


def test_public_department_grouping_carries_instability_warning(engine):
    r = engine(employee_kpi_public=emp([dict()])).compute_grouped("performance.avg_performance_score", E, "department")
    assert any("unstable per employee_id" in w for w in r[0].warnings)
