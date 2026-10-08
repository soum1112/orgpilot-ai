"""Hand-calculated formula checks. Each expected value is derived on paper in the comment."""
import pytest

from kpi_engine import Status
from .conftest import emp, mkt, po

M, P, E = "marketing_daily", "procurement_po", "employee_kpi_public"


def test_marketing_ratio_of_sums_not_mean_of_ratios(engine):
    # a: imp 1000 clk 10 spend 100 rev 300 ord 2 | b: imp 9000 clk 20 spend 300 rev 300 ord 1
    e = engine(marketing_daily=mkt([
        dict(campaign_name="a", impressions=1000, clicks=10, mark_spent=100.0, revenue=300.0, orders=2),
        dict(campaign_name="b", impressions=9000, clicks=20, mark_spent=300.0, revenue=300.0, orders=1)]))
    assert e.compute("marketing.roas", M).value == pytest.approx(600 / 400)          # mean of row ROAS would be 2.0
    assert e.compute("marketing.ctr_pct", M).value == pytest.approx(30 / 10000 * 100)  # mean of row CTR would be 0.611
    assert e.compute("marketing.cost_per_order", M).value == pytest.approx(400 / 3)  # mean of row CPO would be 175


def test_procurement_formulas(engine):
    # P1 q100 u10 n9 def5 lead10 Yes | P2 q200 u20 n18 def-missing lead20 No | P3 q100 u10 n8 def10 lead-missing Yes
    e = engine(procurement_po=po([
        dict(PO_ID="P1", Quantity=100, Unit_Price=10.0, Negotiated_Price=9.0, Defective_Units=5.0,
             Order_Date="2022-01-10", Delivery_Date="2022-01-20", Compliance="Yes"),
        dict(PO_ID="P2", Quantity=200, Unit_Price=20.0, Negotiated_Price=18.0, Defective_Units=None,
             Order_Date="2022-01-10", Delivery_Date="2022-01-30", Compliance="No"),
        dict(PO_ID="P3", Quantity=100, Unit_Price=10.0, Negotiated_Price=8.0, Defective_Units=10.0,
             Order_Date="2022-01-10", Delivery_Date=None, Compliance="Yes")]))
    assert e.compute("procurement.savings_pct", P).value == pytest.approx((100 + 400 + 200) / 6000 * 100)  # value-weighted 11.667
    assert e.compute("procurement.avg_lead_time_days", P).value == pytest.approx(15.0)                    # (10+20)/2
    assert e.compute("procurement.defect_rate_pct", P).value == pytest.approx(15 / 200 * 100)              # 7.5, NOT 15/400
    assert e.compute("procurement.compliance_rate_pct", P).value == pytest.approx(2 / 3 * 100)


def test_employee_formulas(engine):
    e = engine(employee_kpi_public=emp([
        dict(employee_id="A", monthly_hours_worked=160.0, tasks_completed=8, performance_score=10.0, attendance_rate=90.0),
        dict(employee_id="B", monthly_hours_worked=100.0, tasks_completed=2, performance_score=20.0, attendance_rate=100.0)]))
    assert e.compute("performance.avg_performance_score", E).value == pytest.approx(15.0)
    assert e.compute("performance.avg_attendance_rate_pct", E).value == pytest.approx(95.0)
    # ratio of sums 10/260*100 = 3.846; mean of per-row (5.0, 2.0) would be 3.5
    assert e.compute("performance.tasks_per_100h", E).value == pytest.approx(10 / 260 * 100)


def test_result_reports_numerator_denominator_and_rows(engine):
    e = engine(marketing_daily=mkt([dict(mark_spent=200.0, revenue=500.0)]))
    r = e.compute("marketing.roas", M)
    assert (r.numerator_total, r.denominator_total, r.n_rows_used, r.n_rows_input) == (500.0, 200.0, 1, 1)
    assert r.evidence_type.value == "observed" and r.data_source == "public benchmark data"


def test_grouped_results_per_campaign(engine):
    e = engine(marketing_daily=mkt([
        dict(campaign_name="a", mark_spent=100.0, revenue=200.0),
        dict(campaign_name="B ", c_date="2021-02-02", mark_spent=100.0, revenue=50.0)]))
    res = e.compute_grouped("marketing.roas", M, "campaign")
    assert {r.group["campaign"]: r.value for r in res} == {"a": 2.0, "b": 0.5}   # names trimmed + lower-cased


def test_row_order_does_not_change_result(engine):
    import random
    rng = random.Random(7)
    rows = [dict(campaign_name=f"c{i}", mark_spent=rng.uniform(0.1, 1e6), revenue=rng.uniform(0, 1e6)) for i in range(200)]
    a = engine(marketing_daily=mkt(rows)).compute("marketing.roas", M).value
    rng.shuffle(rows)
    b = engine(marketing_daily=mkt(rows)).compute("marketing.roas", M).value
    assert a == b  # exact equality: math.fsum is order independent
