"""Denominators, missing values, invalid rows, schema and unit consistency."""
import numpy as np
import pytest

from kpi_engine import SchemaError, Status
from kpi_engine.engine import KPIEngineError
from .conftest import emp, emp_syn, mkt, po

M, P, E, S = "marketing_daily", "procurement_po", "employee_kpi_public", "employee_kpi_synthetic"


# ---------- denominators
def test_zero_total_spend_gives_none_not_inf_or_zero(engine):
    r = engine(marketing_daily=mkt([dict(mark_spent=0.0, revenue=100.0)])).compute("marketing.roas", M)
    assert r.value is None and r.status == Status.INVALID_DENOMINATOR


def test_zero_total_orders_gives_none(engine):
    r = engine(marketing_daily=mkt([dict(orders=0, revenue=0.0)])).compute("marketing.cost_per_order", M)
    assert r.value is None and r.status == Status.INVALID_DENOMINATOR


def test_zero_order_days_stay_in_numerator_when_total_orders_positive(engine):
    # day1: spend 100, 0 orders | day2: spend 100, 2 orders  -> CPO = 200/2 = 100 (spend on zero-order day is real cost)
    e = engine(marketing_daily=mkt([dict(c_date="2021-02-01", mark_spent=100.0, orders=0, revenue=0.0),
                                    dict(c_date="2021-02-02", mark_spent=100.0, orders=2)]))
    assert e.compute("marketing.cost_per_order", M).value == pytest.approx(100.0)


def test_zero_impressions_gives_none(engine):
    r = engine(marketing_daily=mkt([dict(impressions=0, clicks=0)])).compute("marketing.ctr_pct", M)
    assert r.value is None and r.status == Status.INVALID_DENOMINATOR


def test_zero_hours_rows_excluded_and_all_zero_gives_none(engine):
    e = engine(employee_kpi_public=emp([dict(employee_id="A", monthly_hours_worked=0.0, tasks_completed=5),
                                        dict(employee_id="B", monthly_hours_worked=100.0, tasks_completed=2)]))
    r = e.compute("performance.tasks_per_100h", E)
    assert r.value == pytest.approx(2.0) and r.exclusion_reasons == {"non_positive:monthly_hours_worked": 1}
    e2 = engine(employee_kpi_public=emp([dict(monthly_hours_worked=0.0)]))
    r2 = e2.compute("performance.tasks_per_100h", E)
    assert r2.value is None and r2.status == Status.INVALID_DENOMINATOR


def test_empty_selection_is_no_data(engine):
    r = engine(marketing_daily=mkt([dict()])).compute("marketing.roas", M, filters={"campaign": "nope"})
    assert r.status == Status.NO_DATA and r.value is None and r.n_rows_input == 0


# ---------- missing values
def test_missing_value_excluded_from_numerator_and_denominator(engine):
    # row2 has no revenue: its spend must NOT stay in the denominator -> ROAS = 200/100 = 2.0
    e = engine(marketing_daily=mkt([dict(c_date="2021-02-01", mark_spent=100.0, revenue=200.0),
                                    dict(c_date="2021-02-02", mark_spent=100.0, revenue=np.nan)]))
    r = e.compute("marketing.roas", M)
    assert r.value == pytest.approx(2.0) and r.n_rows_used == 1
    assert r.exclusion_reasons == {"missing:revenue": 1}
    assert any("excluded" in w for w in r.warnings)


def test_all_defects_missing_gives_none_never_zero(engine):
    r = engine(procurement_po=po([dict(PO_ID="1", Defective_Units=None), dict(PO_ID="2", Defective_Units=None)])).compute(
        "procurement.defect_rate_pct", P)
    assert r.value is None and r.status == Status.INVALID_DENOMINATOR


def test_missing_attendance_not_imputed_as_zero(engine):
    e = engine(employee_kpi_public=emp([dict(employee_id="A", attendance_rate=90.0),
                                        dict(employee_id="B", attendance_rate=np.nan)]))
    assert e.compute("performance.avg_attendance_rate_pct", E).value == pytest.approx(90.0)


def test_negative_lead_time_and_missing_delivery_excluded(engine):
    e = engine(procurement_po=po([
        dict(PO_ID="1", Order_Date="2022-01-10", Delivery_Date="2022-01-20"),   # 10
        dict(PO_ID="2", Order_Date="2022-02-27", Delivery_Date="2022-02-22"),   # -5 -> invalid
        dict(PO_ID="3", Order_Date="2022-03-01", Delivery_Date=None)]))        # missing
    r = e.compute("procurement.avg_lead_time_days", P)
    assert r.value == pytest.approx(10.0)
    assert r.exclusion_reasons == {"missing:lead_time_days": 1, "negative:lead_time_days": 1}


def test_zero_day_lead_time_is_valid(engine):
    r = engine(procurement_po=po([dict(Order_Date="2022-01-10", Delivery_Date="2022-01-10")])).compute(
        "procurement.avg_lead_time_days", P)
    assert r.value == 0.0 and r.status == Status.OK


def test_funnel_violation_row_excluded_from_ctr(engine):
    e = engine(marketing_daily=mkt([dict(c_date="2021-02-01", impressions=1000, clicks=10),
                                    dict(c_date="2021-02-02", impressions=100, clicks=500)]))
    r = e.compute("marketing.ctr_pct", M)
    assert r.value == pytest.approx(1.0) and r.exclusion_reasons == {"clicks_exceeds_impressions": 1}


def test_negative_spend_excluded(engine):
    e = engine(marketing_daily=mkt([dict(c_date="2021-02-01", mark_spent=100.0, revenue=100.0),
                                    dict(c_date="2021-02-02", mark_spent=-50.0, revenue=500.0)]))
    r = e.compute("marketing.roas", M)
    assert r.value == pytest.approx(1.0) and r.exclusion_reasons == {"negative:spend": 1}


def test_non_numeric_text_is_missing_and_reported(engine):
    e = engine(marketing_daily=mkt([dict(c_date="2021-02-01", mark_spent=100.0, revenue=200.0),
                                    dict(c_date="2021-02-02", mark_spent="n/a", revenue=500.0)]))
    r = e.compute("marketing.roas", M)
    assert r.value == pytest.approx(2.0)
    assert any("non-numeric" in w for w in r.warnings)


def test_unparseable_date_row_dropped_and_reported(engine):
    r = engine(marketing_daily=mkt([dict(c_date="2021-02-01"), dict(c_date="not a date", campaign_name="b")])).compute(
        "marketing.roas", M)
    assert r.n_rows_input == 1 and any("unparseable or missing date" in w for w in r.warnings)


def test_low_sample_is_flagged_not_hidden(engine):
    r = engine(marketing_daily=mkt([dict()])).compute("marketing.roas", M)
    assert r.status == Status.OK and any(w.startswith("low_sample") for w in r.warnings)


# ---------- schema
def test_missing_required_column_raises_schema_error(engine):
    with pytest.raises(SchemaError):
        engine(marketing_daily=mkt([dict()]).drop(columns=["mark_spent"])).compute("marketing.roas", M)


def test_unknown_kpi_dataset_and_wrong_pairing(engine):
    e = engine(marketing_daily=mkt([dict()]))
    with pytest.raises(KPIEngineError):
        e.compute("nope.kpi", M)
    with pytest.raises(KPIEngineError):
        e.compute("marketing.roas", "procurement_po")
    with pytest.raises(KPIEngineError):
        e.compute("marketing.roas", "no_such_dataset")


# ---------- units
def test_attendance_as_fraction_is_rejected_not_rescaled(engine):
    r = engine(employee_kpi_public=emp([dict(employee_id="A", attendance_rate=0.95),
                                        dict(employee_id="B", attendance_rate=0.90)])).compute(
        "performance.avg_attendance_rate_pct", E)
    assert r.status == Status.INVALID_UNITS and r.value is None
    assert any("fraction" in w for w in r.warnings)


def test_fraction_attendance_does_not_block_other_kpis(engine):
    e = engine(employee_kpi_public=emp([dict(attendance_rate=0.95)]))
    assert e.compute("performance.avg_performance_score", E).status == Status.OK


def test_attendance_above_100_excluded_as_out_of_range(engine):
    e = engine(employee_kpi_public=emp([dict(employee_id="A", attendance_rate=90.0),
                                        dict(employee_id="B", attendance_rate=101.0),
                                        dict(employee_id="C", attendance_rate=-3.0)]))
    r = e.compute("performance.avg_attendance_rate_pct", E)
    assert r.value == pytest.approx(90.0) and r.exclusion_reasons == {"out_of_range:attendance_rate[0,100]": 2}


def _with_currency_column(monkeypatch):
    import dataclasses
    from kpi_engine.datasets import DATASETS
    monkeypatch.setitem(DATASETS, M, dataclasses.replace(DATASETS[M], currency_column="currency"))


def test_mixed_currency_blocks_money_kpis_but_not_ratios_of_counts(engine, monkeypatch):
    _with_currency_column(monkeypatch)
    df = mkt([dict(c_date="2021-02-01"), dict(c_date="2021-02-02")])
    df["currency"] = ["INR", "USD"]
    e = engine(marketing_daily=df)
    assert e.compute("marketing.roas", M).status == Status.INVALID_UNITS
    assert e.compute("marketing.cost_per_order", M).status == Status.INVALID_UNITS
    assert e.compute("marketing.ctr_pct", M).status == Status.OK


def test_single_currency_is_named_in_unit_label(engine, monkeypatch):
    _with_currency_column(monkeypatch)
    df = mkt([dict()])
    df["currency"] = ["inr"]
    assert engine(marketing_daily=df).compute("marketing.cost_per_order", M).unit_label == "INR per order"


def test_currency_not_stated_is_said_plainly(engine):
    r = engine(marketing_daily=mkt([dict()])).compute("marketing.cost_per_order", M)
    assert "not stated" in r.unit_label
