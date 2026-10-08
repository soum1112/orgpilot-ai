"""Profile the CSVs behind the KPI engine -> docs/kpi/dataset_inventory.json (columns, dtypes, nulls, ranges, keys).

    python scripts/profile_datasets.py /path/to/final
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from kpi_engine.datasets import DATASETS  # noqa: E402

DATE_COLS = {"marketing_daily": "c_date", "procurement_po": "Order_Date", "employee_kpi_public": "month", "employee_kpi_synthetic": "month"}
EXTRA = ["public_benchmark/marketing_kpi_by_campaign.csv", "public_benchmark/procurement_kpi_by_supplier.csv",
         "public_benchmark/procurement_kpi_by_quarter.csv", "public_benchmark/employee_kpi_by_department.csv",
         "public_benchmark/employee_kpi_by_month.csv"]


def col_profile(s: pd.Series) -> dict:
    d = {"dtype": str(s.dtype), "nulls": int(s.isna().sum()), "n_unique": int(s.nunique())}
    if pd.api.types.is_numeric_dtype(s) and s.notna().any():
        d.update(min=float(s.min()), max=float(s.max()))
    return d


def main(root: Path) -> None:
    out = {"source_root": str(root), "datasets": {}, "published_summary_files": {}}
    for ds_id, spec in DATASETS.items():
        df = pd.read_csv(root / spec.relative_path)
        keys = {"po_id": "PO_ID"}.get(spec.key_columns[0])
        entry = {"file": spec.relative_path, "data_source": spec.data_source, "rows": len(df), "columns": {c: col_profile(df[c]) for c in df.columns},
                 "exact_duplicate_rows": int(df.duplicated().sum())}
        dc = DATE_COLS[ds_id]
        dates = pd.to_datetime(df[dc], errors="coerce")
        entry["date_column"], entry["date_min"], entry["date_max"] = dc, str(dates.min().date()), str(dates.max().date())
        entry["distinct_periods"] = int(dates.dt.to_period("M").nunique())
        if ds_id == "procurement_po":
            entry["duplicate_PO_ID"] = int(df["PO_ID"].duplicated().sum())
        if ds_id == "marketing_daily":
            entry["duplicate_date_campaign"] = int(df.assign(k=df["campaign_name"].str.lower()).duplicated(["c_date", "k"]).sum())
        if ds_id.startswith("employee"):
            entry["duplicate_employee_month"] = int(df.duplicated(["employee_id", "month"]).sum())
            entry["employee_month_keys_on_multiple_rows"] = int((df.groupby(["employee_id", "month"]).size() > 1).sum())
        out["datasets"][ds_id] = entry
    for rel in EXTRA:
        df = pd.read_csv(root / rel)
        out["published_summary_files"][rel] = {"rows": len(df), "columns": list(df.columns)}
    p = ROOT / "docs" / "kpi" / "dataset_inventory.json"
    p.write_text(json.dumps(out, indent=2) + "\n")
    print("wrote", p)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/final"))
