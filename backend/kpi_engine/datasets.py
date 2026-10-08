"""Dataset specs + preparation (canonical schema, duplicates, units, missingness).

Every dataset the KPI engine can read is described by a DatasetSpec. The spec is also the
provenance record that the registry and the API expose. Nothing here assumes two datasets
share a company, population or period: each has its own ``entity_scope`` and observed period.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd

PUBLIC = "public benchmark data"
SYNTHETIC = "synthetic demo data"

CONFLICT_POLICIES = ("keep", "exclude")


class SchemaError(ValueError):
    """Raised when a raw file is missing columns the spec requires."""


# --------------------------------------------------------------------------- specs
@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    display_name: str
    data_source: str                      # PUBLIC | SYNTHETIC
    entity_scope: str                     # who/what the rows describe; used for comparability
    relative_path: str                    # relative to the dataset root (the 'final/' folder)
    grain: str                            # what one row is
    key_columns: tuple[str, ...]          # canonical columns that should identify a row
    key_semantics: str                    # 'primary' (dup key = error) | 'record_level'
    date_grain: str                       # 'day' | 'month'
    declared_period: str                  # documented period (verified by a test)
    raw_required: tuple[str, ...]
    column_map: Mapping[str, str]         # raw -> canonical (plain renames)
    derived: Mapping[str, tuple[str, ...]]  # canonical derived column -> raw inputs
    group_columns: tuple[str, ...]        # canonical columns usable for filters / group_by
    provenance: Mapping[str, Any]
    percent_columns: tuple[str, ...] = ()
    currency: str | None = None           # None = not stated in the source
    currency_column: str | None = None    # optional raw column holding a currency code
    default_conflict_policy: str = "exclude"
    group_warnings: Mapping[str, str] = field(default_factory=dict)
    derived_from_ranges_of: str | None = None
    notes: tuple[str, ...] = ()

    def raw_columns_for(self, canonical: str) -> tuple[str, ...]:
        """Raw source columns behind a canonical column (empty for 'one')."""
        if canonical in self.derived:
            return self.derived[canonical]
        return tuple(r for r, c in self.column_map.items() if c == canonical)


_NOT_STATED = {"url": None, "license": None, "status": "TO BE COMPLETED (README section 4): exact URL and license not supplied"}


def _build_specs() -> dict[str, DatasetSpec]:
    marketing = DatasetSpec(
        dataset_id="marketing_daily",
        display_name="Marketing campaign performance (daily)",
        data_source=PUBLIC,
        entity_scope="public:marketing_ad_campaigns_unspecified_advertiser",
        relative_path="public_benchmark/marketing_kpi_daily.csv",
        grain="one row per campaign per day",
        key_columns=("date", "campaign"),
        key_semantics="primary",
        date_grain="day",
        declared_period="2021-02-01 to 2021-02-28",
        raw_required=("c_date", "campaign_name", "category", "impressions", "clicks", "leads", "orders", "mark_spent", "revenue"),
        column_map={"c_date": "date", "campaign_name": "campaign", "category": "category", "impressions": "impressions",
                    "clicks": "clicks", "leads": "leads", "orders": "orders", "mark_spent": "spend", "revenue": "revenue"},
        derived={},
        group_columns=("campaign", "category"),
        provenance=_NOT_STATED,
        notes=("Currency is not stated in the source; amounts are reported as 'currency units'.",
               "Raw campaign_name has one casing inconsistency (facebOOK_tier2); the engine lower-cases names.",
               "Revenue is gross revenue, not margin."),
    )
    procurement = DatasetSpec(
        dataset_id="procurement_po",
        display_name="Procurement purchase orders",
        data_source=PUBLIC,
        entity_scope="public:procurement_5_suppliers_unspecified_buyer",
        relative_path="public_benchmark/procurement_kpi_po_level.csv",
        grain="one row per purchase order (PO_ID)",
        key_columns=("po_id",),
        key_semantics="primary",
        date_grain="day",
        declared_period="order dates 2022-01-01 to 2024-01-01",
        raw_required=("PO_ID", "Supplier", "Item_Category", "Order_Status", "Order_Date", "Delivery_Date", "Quantity",
                      "Unit_Price", "Negotiated_Price", "Defective_Units", "Compliance"),
        column_map={"PO_ID": "po_id", "Supplier": "supplier", "Item_Category": "item_category", "Order_Status": "status",
                    "Order_Date": "date", "Quantity": "quantity", "Unit_Price": "unit_price",
                    "Negotiated_Price": "negotiated_price", "Defective_Units": "defective_units"},
        derived={"delivery_date": ("Delivery_Date",),
                 "po_value_list": ("Quantity", "Unit_Price"),
                 "savings_value": ("Quantity", "Unit_Price", "Negotiated_Price"),
                 "lead_time_days": ("Order_Date", "Delivery_Date"),
                 "is_compliant": ("Compliance",)},
        group_columns=("supplier", "item_category", "status"),
        provenance=_NOT_STATED,
        notes=("Time filtering uses Order_Date, not Delivery_Date.",
               "Currency is not stated in the source.",
               "Status vs date fields are inconsistent in the source (Cancelled/Pending POs carry delivery dates; 68 Delivered POs have none).",
               "Derived columns in the file (Savings, PO_Value_*, Lead_Time_*) are NOT used; the engine recomputes from raw columns."),
    )
    emp_pub = DatasetSpec(
        dataset_id="employee_kpi_public",
        display_name="Employee monthly KPIs (public benchmark)",
        data_source=PUBLIC,
        entity_scope="public:employee_performance_E1000-E1099_unspecified_employer",
        relative_path="public_benchmark/employee_kpi_records.csv",
        grain="one row per employee-id per month (record level; 200 employee-month keys appear twice)",
        key_columns=("employee_id", "month_key"),
        key_semantics="record_level",
        date_grain="month",
        declared_period="2024-01 to 2024-11 (2024-02 absent)",
        raw_required=("employee_id", "department", "month", "monthly_hours_worked", "attendance_rate", "tasks_completed",
                      "performance_score", "training_hours", "peer_review_score", "manager_rating"),
        column_map={"employee_id": "employee_id", "department": "department", "month": "date",
                    "monthly_hours_worked": "monthly_hours_worked", "attendance_rate": "attendance_rate",
                    "tasks_completed": "tasks_completed", "performance_score": "performance_score",
                    "training_hours": "training_hours", "peer_review_score": "peer_review_score",
                    "manager_rating": "manager_rating"},
        derived={"month_key": ("month",)},
        group_columns=("department",),
        percent_columns=("attendance_rate",),
        provenance=_NOT_STATED,
        default_conflict_policy="keep",
        group_warnings={"department": "Department is unstable per employee_id in the source (about 4.6 departments per id); "
                                      "use department results at record level only, never as an employee trajectory."},
        notes=("performance_score scale is undocumented (observed 0 to 30.89).",
               "department_map.csv translates only 5 public department names (Finance, HR, IT, Marketing, Sales)."),
    )
    emp_syn = DatasetSpec(
        dataset_id="employee_kpi_synthetic",
        display_name="Employee monthly KPIs (synthetic company: Timeless Software Pvt. Ltd.)",
        data_source=SYNTHETIC,
        entity_scope="synthetic:timeless_software_pvt_ltd",
        relative_path="synthetic/employee_kpi_monthly.csv",
        grain="one row per employee per month",
        key_columns=("employee_id", "month_key"),
        key_semantics="primary",
        date_grain="month",
        declared_period="2026-01 to 2026-09",
        raw_required=("kpi_record_id", "employee_id", "department_id", "month", "monthly_hours_worked", "attendance_rate",
                      "tasks_completed", "performance_score", "training_hours", "peer_review_score", "manager_rating"),
        column_map={"employee_id": "employee_id", "department_id": "department", "month": "date",
                    "monthly_hours_worked": "monthly_hours_worked", "attendance_rate": "attendance_rate",
                    "tasks_completed": "tasks_completed", "performance_score": "performance_score",
                    "training_hours": "training_hours", "peer_review_score": "peer_review_score",
                    "manager_rating": "manager_rating"},
        derived={"month_key": ("month",)},
        group_columns=("department",),
        percent_columns=("attendance_rate",),
        provenance={"url": None, "license": None, "status": "Generated by the team (README section 4); invented records"},
        derived_from_ranges_of="employee_kpi_public",
        notes=("Value ranges were copied from the public employee file; no public record is linked to any synthetic employee.",
               "'department' holds the department_id code (ENG, QA, ...)."),
    )
    return {s.dataset_id: s for s in (marketing, procurement, emp_pub, emp_syn)}


DATASETS: dict[str, DatasetSpec] = _build_specs()


# --------------------------------------------------------------------------- canonicalisation
def _num(raw: pd.DataFrame, col: str, coerced: dict[str, int], name: str) -> pd.Series:
    s = pd.to_numeric(raw[col], errors="coerce").astype("float64")
    bad = int((raw[col].notna() & s.isna()).sum())
    if bad:
        coerced[name] = coerced.get(name, 0) + bad
    return s


def _str(raw: pd.DataFrame, col: str, lower: bool = False) -> pd.Series:
    def f(v: Any) -> Any:
        if not isinstance(v, str):
            return None
        v = v.strip()
        return v.lower() if lower else v
    return raw[col].astype("object").map(f).astype("object")


def _canon_marketing(raw: pd.DataFrame, coerced: dict[str, int]) -> pd.DataFrame:
    df = pd.DataFrame(index=raw.index)
    df["date"] = pd.to_datetime(raw["c_date"], errors="coerce")
    df["campaign"] = _str(raw, "campaign_name", lower=True)
    df["category"] = _str(raw, "category", lower=True)
    for c in ("impressions", "clicks", "leads", "orders", "revenue"):
        df[c] = _num(raw, c, coerced, c)
    df["spend"] = _num(raw, "mark_spent", coerced, "spend")
    return df


def _canon_procurement(raw: pd.DataFrame, coerced: dict[str, int]) -> pd.DataFrame:
    df = pd.DataFrame(index=raw.index)
    df["po_id"] = _str(raw, "PO_ID")
    df["supplier"] = _str(raw, "Supplier")
    df["item_category"] = _str(raw, "Item_Category")
    df["status"] = _str(raw, "Order_Status")
    df["date"] = pd.to_datetime(raw["Order_Date"], errors="coerce")
    df["delivery_date"] = pd.to_datetime(raw["Delivery_Date"], errors="coerce")
    qty = _num(raw, "Quantity", coerced, "quantity")
    unit = _num(raw, "Unit_Price", coerced, "unit_price")
    neg = _num(raw, "Negotiated_Price", coerced, "negotiated_price")
    df["quantity"], df["unit_price"], df["negotiated_price"] = qty, unit, neg
    df["defective_units"] = _num(raw, "Defective_Units", coerced, "defective_units")
    df["po_value_list"] = qty * unit
    df["savings_value"] = qty * (unit - neg)
    df["lead_time_days"] = (df["delivery_date"] - df["date"]).dt.days.astype("float64")
    comp = raw["Compliance"].astype("object").map(lambda v: v.strip().lower() if isinstance(v, str) else None)
    df["is_compliant"] = comp.map({"yes": 1.0, "no": 0.0}).astype("float64")
    unknown = int((comp.notna() & df["is_compliant"].isna()).sum())
    if unknown:
        coerced["is_compliant"] = unknown
    return df


def _canon_employee(raw: pd.DataFrame, coerced: dict[str, int], dept_col: str) -> pd.DataFrame:
    df = pd.DataFrame(index=raw.index)
    df["employee_id"] = _str(raw, "employee_id")
    df["department"] = _str(raw, dept_col)
    month = raw["month"].astype("object").map(lambda v: v.strip() if isinstance(v, str) else v)
    df["date"] = pd.to_datetime(month, format="%Y-%m", errors="coerce")
    df["month_key"] = df["date"].dt.strftime("%Y-%m")
    for c in ("monthly_hours_worked", "attendance_rate", "tasks_completed", "performance_score",
              "training_hours", "peer_review_score", "manager_rating"):
        df[c] = _num(raw, c, coerced, c)
    return df


_CANON: dict[str, Callable[[pd.DataFrame, dict[str, int]], pd.DataFrame]] = {
    "marketing_daily": _canon_marketing,
    "procurement_po": _canon_procurement,
    "employee_kpi_public": lambda r, c: _canon_employee(r, c, "department"),
    "employee_kpi_synthetic": lambda r, c: _canon_employee(r, c, "department_id"),
}


# --------------------------------------------------------------------------- preparation
@dataclass
class QualityReport:
    dataset_id: str
    rows_raw: int = 0
    rows_after_cleaning: int = 0
    invalid_date_rows_dropped: int = 0
    exact_duplicate_rows_dropped: int = 0
    conflicting_key_groups: int = 0
    conflicting_key_rows: int = 0
    conflict_policy: str = "exclude"
    conflict_rows_dropped: int = 0
    non_numeric_values_coerced: dict[str, int] = field(default_factory=dict)
    missing_by_column: dict[str, int] = field(default_factory=dict)
    flags: dict[str, str] = field(default_factory=dict)     # unit / scale problems
    observed_start: str | None = None
    observed_end: str | None = None

    def warnings(self) -> list[str]:
        w: list[str] = []
        if self.invalid_date_rows_dropped:
            w.append(f"{self.invalid_date_rows_dropped} rows dropped: unparseable or missing date")
        if self.exact_duplicate_rows_dropped:
            w.append(f"{self.exact_duplicate_rows_dropped} exact duplicate rows removed")
        if self.conflicting_key_groups:
            action = "kept (record-level data)" if self.conflict_policy == "keep" else "excluded"
            w.append(f"{self.conflicting_key_groups} keys appear on multiple non-identical rows "
                     f"({self.conflicting_key_rows} rows), {action} under policy '{self.conflict_policy}'")
        for col, n in sorted(self.non_numeric_values_coerced.items()):
            w.append(f"{n} non-numeric values in '{col}' treated as missing")
        for msg in self.flags.values():
            w.append(msg)
        return w

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class PreparedDataset:
    spec: DatasetSpec
    df: pd.DataFrame
    quality: QualityReport
    currency: str | None


def load_raw(spec: DatasetSpec, data_dir: str | Path) -> pd.DataFrame:
    path = Path(data_dir) / spec.relative_path
    if not path.exists():
        raise FileNotFoundError(f"dataset file not found: {path}")
    return pd.read_csv(path)


def prepare(spec: DatasetSpec, raw: pd.DataFrame, conflict_policy: str | None = None) -> PreparedDataset:
    policy = conflict_policy or spec.default_conflict_policy
    if policy not in CONFLICT_POLICIES:
        raise ValueError(f"conflict_policy must be one of {CONFLICT_POLICIES}")
    missing = [c for c in spec.raw_required if c not in raw.columns]
    if missing:
        raise SchemaError(f"{spec.dataset_id}: missing required columns {missing}")

    raw = raw.reset_index(drop=True)
    q = QualityReport(dataset_id=spec.dataset_id, rows_raw=len(raw), conflict_policy=policy)
    df = _CANON[spec.dataset_id](raw, q.non_numeric_values_coerced)

    currency = spec.currency
    if spec.currency_column and spec.currency_column in raw.columns:
        codes = _str(raw, spec.currency_column).map(lambda v: v.upper() if isinstance(v, str) else None)
        distinct = sorted(set(codes.dropna()))
        if len(distinct) > 1:
            q.flags["mixed_currency"] = f"mixed currencies in source ({', '.join(distinct)}); monetary KPIs are not computed"
        elif len(distinct) == 1:
            currency = distinct[0]

    # rows without a usable date cannot be time-filtered or trended
    bad_date = df["date"].isna()
    q.invalid_date_rows_dropped = int(bad_date.sum())
    df = df.loc[~bad_date]

    # exact duplicates (every canonical column identical)
    exact = df.duplicated(keep="first")
    q.exact_duplicate_rows_dropped = int(exact.sum())
    df = df.loc[~exact]

    # same key, different content
    keys = list(spec.key_columns)
    conflict = df.duplicated(subset=keys, keep=False)
    if conflict.any():
        q.conflicting_key_rows = int(conflict.sum())
        q.conflicting_key_groups = int(df.loc[conflict, keys].drop_duplicates().shape[0])
        if policy == "exclude":
            q.conflict_rows_dropped = int(conflict.sum())
            df = df.loc[~conflict]

    # unit / scale sanity: a column declared as percent 0-100 must not look like a 0-1 fraction
    for col in spec.percent_columns:
        vals = df[col].dropna()
        if len(vals) and 0 < vals.max() <= 1.0:
            q.flags[f"unit_suspect:{col}"] = (f"'{col}' is declared as a percentage (0-100) but every value is within 0-1; "
                                              f"likely a fraction. KPIs using it are not computed.")

    df = df.copy()
    df["one"] = 1.0
    df = df.reset_index(drop=True)

    measure_cols = [c for c in df.columns if df[c].dtype.kind == "f" and c != "one"]
    q.missing_by_column = {c: int(df[c].isna().sum()) for c in measure_cols if df[c].isna().any()}
    q.rows_after_cleaning = len(df)
    if len(df):
        q.observed_start = df["date"].min().strftime("%Y-%m" if spec.date_grain == "month" else "%Y-%m-%d")
        q.observed_end = df["date"].max().strftime("%Y-%m" if spec.date_grain == "month" else "%Y-%m-%d")
    return PreparedDataset(spec=spec, df=df, quality=q, currency=currency)
