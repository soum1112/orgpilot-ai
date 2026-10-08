"""The engine must reproduce the team's published summary files from raw rows (real data)."""
import pandas as pd
import pytest

from kpi_engine import DATASETS, Status

M, P, E, S = "marketing_daily", "procurement_po", "employee_kpi_public", "employee_kpi_synthetic"
REL = 1e-9


def _by(results):
    return {r.group[next(iter(r.group))]: r.value for r in results}


def test_marketing_by_campaign_matches_published_file(real_engine, data_dir):
    pub = pd.read_csv(data_dir / "public_benchmark" / "marketing_kpi_by_campaign.csv").set_index("campaign_name_clean")
    for key, col in (("marketing.roas", "ROAS"), ("marketing.ctr_pct", "CTR_pct"), ("marketing.cost_per_order", "CPO")):
        got = _by(real_engine.compute_grouped(key, M, "campaign"))
        assert set(got) == set(pub.index)
        for name, v in got.items():
            assert v == pytest.approx(pub.loc[name, col], rel=REL), (key, name)


def test_marketing_campaign_names_equal_team_cleaned_names(real_engine, data_dir):
    raw = pd.read_csv(data_dir / "public_benchmark" / "marketing_kpi_daily.csv")
    assert set(real_engine.dataset(M).df["campaign"]) == set(raw["campaign_name_clean"])


def test_marketing_overall_numbers(real_engine):
    r = real_engine.compute("marketing.roas", M)
    assert r.status == Status.OK and r.n_rows_used == 308 and r.value == pytest.approx(42889366.0 / 30590879.82, rel=REL)
    assert real_engine.compute("marketing.cost_per_order", M).value == pytest.approx(3803.4166, abs=1e-3)


def test_procurement_by_supplier_matches_published_file(real_engine, data_dir):
    pub = pd.read_csv(data_dir / "public_benchmark" / "procurement_kpi_by_supplier.csv").set_index("Supplier")
    pairs = (("procurement.savings_pct", "Savings_pct"), ("procurement.compliance_rate_pct", "Compliance_rate_pct"),
             ("procurement.defect_rate_pct", "Defect_rate_pct"), ("procurement.avg_lead_time_days", "Avg_lead_time_days"))
    for key, col in pairs:
        got = _by(real_engine.compute_grouped(key, P, "supplier"))
        for name, v in got.items():
            assert v == pytest.approx(pub.loc[name, col], rel=REL), (key, name)


def test_procurement_by_quarter_matches_published_file_and_flags_2024q1(real_engine, data_dir):
    pub = pd.read_csv(data_dir / "public_benchmark" / "procurement_kpi_by_quarter.csv").set_index("Order_Quarter")
    for key, col in (("procurement.savings_pct", "Savings_pct"), ("procurement.compliance_rate_pct", "Compliance_rate_pct"),
                     ("procurement.defect_rate_pct", "Defect_rate_pct"), ("procurement.avg_lead_time_days", "Avg_lead_time_days")):
        t = real_engine.trend(key, P, "quarter")
        assert [p.period for p in t.points] == list(pub.index)
        for p in t.points:
            if p.value is not None:
                assert p.value == pytest.approx(pub.loc[p.period, col], rel=REL), (key, p.period)
    last = real_engine.trend("procurement.savings_pct", P, "quarter").points[-1]
    assert last.period == "2024Q1" and last.low_sample and last.partial_period and last.change_abs is None


def test_defect_rate_uses_units_weighted_denominator_not_all_quantity(real_engine):
    r = real_engine.compute("procurement.defect_rate_pct", P)
    assert r.value == pytest.approx(6.8025, abs=1e-4) and r.exclusion_reasons == {"missing:defective_units": 136}
    naive = r.numerator_total / real_engine.dataset(P).df["quantity"].sum() * 100
    assert naive == pytest.approx(5.6374, abs=1e-4) and naive != pytest.approx(r.value, abs=0.5)


def test_lead_time_exclusions_match_documented_data_quality(real_engine):
    r = real_engine.compute("procurement.avg_lead_time_days", P)
    assert r.exclusion_reasons == {"missing:lead_time_days": 87, "negative:lead_time_days": 1}
    assert r.n_rows_used == 689 and any("Cancelled/Pending" in w for w in r.warnings)


def test_public_employee_by_department_and_month_match_published_files(real_engine, data_dir):
    dept = pd.read_csv(data_dir / "public_benchmark" / "employee_kpi_by_department.csv").set_index("department")
    got = _by(real_engine.compute_grouped("performance.avg_performance_score", E, "department"))
    for name, v in got.items():
        assert v == pytest.approx(dept.loc[name, "avg_perf"], rel=REL)
    att = _by(real_engine.compute_grouped("performance.avg_attendance_rate_pct", E, "department"))
    for name, v in att.items():
        assert v == pytest.approx(dept.loc[name, "avg_attendance"], rel=REL)
    month = pd.read_csv(data_dir / "public_benchmark" / "employee_kpi_by_month.csv").set_index("month")
    t = real_engine.trend("performance.avg_performance_score", E, "month")
    assert t.gap_periods == ["2024-02"]                      # the month the source file skips
    for p in t.points:
        if p.status == Status.OK:
            assert p.value == pytest.approx(month.loc[p.period, "avg_perf"], rel=REL)


def test_public_employee_duplicate_keys_reported(real_engine):
    q = real_engine.dataset(E).quality
    assert (q.conflicting_key_groups, q.conflicting_key_rows, q.exact_duplicate_rows_dropped) == (200, 400, 0)
    assert q.conflict_policy == "keep" and q.rows_after_cleaning == 1200


def test_synthetic_customer_support_has_lowest_performance(real_engine):
    got = _by(real_engine.compute_grouped("performance.avg_performance_score", S, "department"))
    assert min(got, key=got.get) == "SUP"   # documented demo finding (README section 7)
    assert real_engine.dataset(S).quality.conflicting_key_groups == 0


def test_observed_periods_match_declared_periods(real_engine):
    expect = {M: ("2021-02-01", "2021-02-28"), P: ("2022-01-01", "2024-01-01"), E: ("2024-01", "2024-11"), S: ("2026-01", "2026-09")}
    for ds, (a, b) in expect.items():
        q = real_engine.dataset(ds).quality
        assert (q.observed_start, q.observed_end) == (a, b)
        assert a in DATASETS[ds].declared_period and b in DATASETS[ds].declared_period


def test_registry_source_columns_exist_in_the_csv_headers(data_dir):
    from kpi_engine.registry import REGISTRY, source_columns
    for d in REGISTRY.values():
        for ds in d.datasets:
            header = set(pd.read_csv(data_dir / DATASETS[ds].relative_path, nrows=0).columns)
            assert set(source_columns(d, ds)) <= header, (d.key, ds)


def test_real_cross_dataset_comparisons_are_refused(real_engine):
    assert not real_engine.check_comparability(E, S, "performance.avg_performance_score")["comparable"]
    assert not real_engine.check_comparability(M, P)["comparable"]


def test_savings_equals_team_map_formula_on_derived_po_value_columns(real_engine, data_dir):
    """kpi_column_map R01 uses PO_Value_List/PO_Value_Negotiated; the engine recomputes from raw Quantity x price."""
    raw = pd.read_csv(data_dir / "public_benchmark" / "procurement_kpi_po_level.csv")
    team = (raw.PO_Value_List.sum() - raw.PO_Value_Negotiated.sum()) / raw.PO_Value_List.sum() * 100
    assert real_engine.compute("procurement.savings_pct", P).value == pytest.approx(team, rel=REL)
    # and the derived columns really are Quantity x price (so the two routes cannot diverge)
    assert ((raw.PO_Value_List - raw.Quantity * raw.Unit_Price).abs().max() < 1e-6)
    assert ((raw.PO_Value_Negotiated - raw.Quantity * raw.Negotiated_Price).abs().max() < 1e-6)
