"""Date filtering semantics and trends (gaps, low sample, partial periods)."""
import pytest

from kpi_engine import Status
from kpi_engine.engine import KPIEngineError
from .conftest import emp, mkt, po

M, P, E = "marketing_daily", "procurement_po", "employee_kpi_public"


def _days(n, **kw):
    return mkt([dict(c_date=f"2021-02-{d:02d}", **kw) for d in range(1, n + 1)])


# ---------- filtering
def test_day_filter_is_inclusive_on_both_ends(engine):
    e = engine(marketing_daily=_days(5))
    r = e.compute("marketing.roas", M, date_from="2021-02-02", date_to="2021-02-04")
    assert r.n_rows_input == 3 and r.period["start"] == "2021-02-02" and r.period["end"] == "2021-02-04"


def test_filter_accepts_date_objects_and_timestamps_with_time(engine):
    import datetime as dt
    e = engine(marketing_daily=_days(5))
    r = e.compute("marketing.roas", M, date_from=dt.date(2021, 2, 3), date_to="2021-02-03T23:59:00")
    assert r.n_rows_input == 1


def test_month_grain_filter_compares_whole_months(engine):
    e = engine(employee_kpi_public=emp([dict(employee_id=f"E{i}", month=f"2024-0{i}") for i in (1, 2, 3, 4)]))
    r = e.compute("performance.avg_performance_score", E, date_from="2024-02-15", date_to="2024-03-01")
    assert r.n_rows_input == 2 and (r.period["start"], r.period["end"]) == ("2024-02", "2024-03")


def test_from_after_to_and_garbage_dates_are_rejected(engine):
    e = engine(marketing_daily=_days(3))
    with pytest.raises(KPIEngineError):
        e.compute("marketing.roas", M, date_from="2021-02-03", date_to="2021-02-01")
    with pytest.raises(KPIEngineError):
        e.compute("marketing.roas", M, date_from="banana")


def test_window_outside_data_is_no_data(engine):
    r = engine(marketing_daily=_days(3)).compute("marketing.roas", M, date_from="2022-01-01")
    assert r.status == Status.NO_DATA and r.value is None


def test_procurement_filters_on_order_date_not_delivery_date(engine):
    e = engine(procurement_po=po([dict(PO_ID="1", Order_Date="2021-12-30", Delivery_Date="2022-01-05"),
                                  dict(PO_ID="2", Order_Date="2022-01-02", Delivery_Date="2022-01-09")]))
    r = e.compute("procurement.avg_lead_time_days", P, date_from="2022-01-01")
    assert r.n_rows_input == 1 and r.value == 7.0


def test_filters_are_case_insensitive_lists_and_unknown_column_rejected(engine):
    e = engine(marketing_daily=mkt([dict(campaign_name="A", c_date="2021-02-01"), dict(campaign_name="b", c_date="2021-02-02"),
                                    dict(campaign_name="c", c_date="2021-02-03")]))
    assert e.compute("marketing.roas", M, filters={"campaign": ["a", "B"]}).n_rows_input == 2
    with pytest.raises(KPIEngineError):
        e.compute("marketing.roas", M, filters={"revenue": 1})
    with pytest.raises(KPIEngineError):
        e.compute_grouped("marketing.roas", M, group_by="impressions")


# ---------- trends
def test_weekly_trend_labels_and_change(engine):
    # 2021-02-01 is a Monday (ISO week 5). Week 1 ROAS 2.0, week 2 ROAS 3.0
    rows = [dict(c_date=f"2021-02-{d:02d}", campaign_name="a", mark_spent=100.0, revenue=200.0) for d in range(1, 8)]
    rows += [dict(c_date=f"2021-02-{d:02d}", campaign_name="a", mark_spent=100.0, revenue=300.0) for d in range(8, 15)]
    t = engine(marketing_daily=mkt(rows)).trend("marketing.roas", M, "week", min_sample=5)
    assert [p.period for p in t.points] == ["2021-W05", "2021-W06"]
    assert [p.value for p in t.points] == [2.0, 3.0]
    assert t.points[1].change_abs == pytest.approx(1.0) and t.points[1].change_pct == pytest.approx(50.0)
    assert not any(p.partial_period for p in t.points) and t.gap_periods == []


def test_trend_uses_ratio_of_sums_per_period_not_mean_of_daily_values(engine):
    rows = [dict(c_date="2021-02-01", mark_spent=100.0, revenue=100.0),   # roas 1
            dict(c_date="2021-02-02", mark_spent=900.0, revenue=2700.0)]  # roas 3 -> sum ratio 2800/1000 = 2.8
    t = engine(marketing_daily=mkt(rows)).trend("marketing.roas", M, "month")
    assert t.points[0].value == pytest.approx(2.8)


def test_gap_month_is_listed_and_no_change_is_computed_across_it(engine):
    e = engine(employee_kpi_public=emp([dict(employee_id=f"E{i}", month=m, performance_score=10.0 + i)
                                        for i, m in enumerate(["2024-01", "2024-01", "2024-03", "2024-03"])]))
    t = e.trend("performance.avg_performance_score", E, "month", min_sample=1)
    assert t.gap_periods == ["2024-02"]
    assert [p.period for p in t.points] == ["2024-01", "2024-02", "2024-03"]
    feb, mar = t.points[1], t.points[2]
    assert feb.status == Status.NO_DATA and feb.value is None
    assert mar.change_abs is None and "gap" in mar.change_note
    assert any("2024-02" in w for w in t.warnings)


def test_low_sample_period_flagged_and_no_change_across_it(engine):
    rows = [dict(employee_id=f"E{i}", month="2024-01", performance_score=10.0) for i in range(12)]
    rows += [dict(employee_id="X", month="2024-02", performance_score=30.0)]
    t = engine(employee_kpi_public=emp(rows)).trend("performance.avg_performance_score", E, "month")  # min_sample 10
    assert t.points[1].low_sample and t.points[1].change_abs is None and "low sample" in t.points[1].change_note


def test_partial_last_period_is_flagged_and_not_compared(engine):
    # quarter 2022Q1 has orders on every month start; 2022Q2 only on 1 April
    rows = [dict(PO_ID=f"A{i}", Order_Date=d, Delivery_Date=None) for i, d in enumerate(
        ["2022-01-01", "2022-02-01", "2022-03-31"] * 4)]
    rows += [dict(PO_ID=f"B{i}", Order_Date="2022-04-01", Delivery_Date=None) for i in range(12)]
    t = engine(procurement_po=po(rows)).trend("procurement.compliance_rate_pct", P, "quarter")
    q1, q2 = t.points
    assert not q1.partial_period and q2.partial_period
    assert q2.change_abs is None and "partly covered" in q2.change_note


def test_single_month_of_data_cannot_state_a_trend(engine):
    t = engine(marketing_daily=_days(28)).trend("marketing.roas", M, "month")
    assert len(t.points) == 1
    assert any("no trend can be stated" in w for w in t.warnings)


def test_frequency_finer_than_grain_is_rejected(engine):
    e = engine(employee_kpi_public=emp([dict()]))
    with pytest.raises(KPIEngineError):
        e.trend("performance.avg_performance_score", E, "week")
    with pytest.raises(KPIEngineError):
        e.trend("performance.avg_performance_score", E, "decade")


def test_trend_respects_filters_and_dates(engine):
    rows = [dict(c_date=f"2021-02-{d:02d}", campaign_name=c, mark_spent=100.0, revenue=100.0 * (1 + (c == "b")))
            for d in range(1, 8) for c in ("a", "b")]
    t = engine(marketing_daily=mkt(rows)).trend("marketing.roas", M, "day", filters={"campaign": "b"},
                                                date_from="2021-02-02", date_to="2021-02-03")
    assert [p.period for p in t.points] == ["2021-02-02", "2021-02-03"] and all(p.value == 2.0 for p in t.points)


def test_trend_with_unit_problem_returns_no_points(engine):
    t = engine(employee_kpi_public=emp([dict(attendance_rate=0.9)])).trend("performance.avg_attendance_rate_pct", E, "month")
    assert t.points == [] and any("fraction" in w for w in t.warnings)
