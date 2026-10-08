"""Shared builders: tiny raw-schema frames with hand-calculable numbers."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from kpi_engine import KPIEngine

MKT_DEFAULT = dict(c_date="2021-02-01", campaign_name="a", category="social", impressions=1000, clicks=10,
                   leads=5, orders=1, mark_spent=100.0, revenue=250.0)
PO_DEFAULT = dict(PO_ID="PO-1", Supplier="S1", Item_Category="MRO", Order_Status="Delivered", Order_Date="2022-01-10",
                  Delivery_Date="2022-01-20", Quantity=100, Unit_Price=10.0, Negotiated_Price=9.0, Defective_Units=5.0,
                  Compliance="Yes")
EMP_DEFAULT = dict(employee_id="E1", department="IT", month="2024-01", monthly_hours_worked=160.0, attendance_rate=95.0,
                   tasks_completed=8, performance_score=10.0, training_hours=4.0, peer_review_score=7.0, manager_rating=7.0)


def _frame(default: dict, rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{**default, **r} for r in rows])


def mkt(rows):
    return _frame(MKT_DEFAULT, rows)


def po(rows):
    return _frame(PO_DEFAULT, rows)


def emp(rows):
    return _frame(EMP_DEFAULT, rows)


def emp_syn(rows):
    df = _frame(EMP_DEFAULT, rows).rename(columns={"department": "department_id"})
    df["kpi_record_id"] = [f"KPI-{i}" for i in range(len(df))]
    return df


@pytest.fixture
def engine():
    def make(**frames):
        return KPIEngine(frames=frames)
    return make


def _data_dir() -> Path | None:
    cands = [os.environ.get("ORGPILOT_DATA_DIR"), str(Path(__file__).resolve().parents[3] / "data" / "final")]
    for c in cands:
        if c and (Path(c) / "public_benchmark").exists():
            return Path(c)
    return None


@pytest.fixture(scope="session")
def data_dir():
    d = _data_dir()
    if d is None:
        pytest.skip("real dataset folder not found (set ORGPILOT_DATA_DIR to the 'final/' folder)")
    return d


@pytest.fixture(scope="session")
def real_engine(data_dir):
    return KPIEngine(data_dir=data_dir)
