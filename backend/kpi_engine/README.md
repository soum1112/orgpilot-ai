# kpi_engine: shared KPI calculation service (v0.1.0)

Pure Python + pandas. **No Django imports**, so the Django/DRF layer (and Member 1/4 code) can import it unchanged.

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install "pandas>=2.2" numpy pytest
export ORGPILOT_DATA_DIR=/path/to/OrgPilot_Dataset_Final/final     # enables the real-data reconciliation tests
pytest                                                              # from the repo root (pytest.ini sets pythonpath=backend)
python scripts/export_kpi_registry.py                               # regenerate docs/kpi/kpi_registry.json + KPI_REGISTRY.md
python scripts/profile_datasets.py "$ORGPILOT_DATA_DIR"             # regenerate docs/kpi/dataset_inventory.json
```

On Windows PowerShell, use the following instead of `source` and `export`:

```powershell
.\.venv\Scripts\Activate.ps1
$env:ORGPILOT_DATA_DIR = "C:\path\to\OrgPilot_Dataset_Final\final"
pytest
```

For this checkout, the dataset path is:

```powershell
$env:ORGPILOT_DATA_DIR = "path"
```

In Command Prompt, use `set "ORGPILOT_DATA_DIR=C:\path\to\OrgPilot_Dataset_Final\final"` instead.

Without `ORGPILOT_DATA_DIR`, the 15 real-data tests are skipped (88 synthetic-frame tests still run).

## Use
```python
from kpi_engine import KPIEngine, TargetSpec
eng = KPIEngine(data_dir="data/final")
eng.compute("marketing.roas", "marketing_daily", date_from="2021-02-01", filters={"category": "search"}).to_dict()
eng.compute_grouped("procurement.defect_rate_pct", "procurement_po", "supplier")
eng.trend("procurement.savings_pct", "procurement_po", "quarter")
eng.compute("marketing.roas", "marketing_daily", target=TargetSpec(1.5, "Q1 plan, doc ref ..."))  # a target needs a source
eng.check_comparability("employee_kpi_public", "employee_kpi_synthetic", "performance.avg_performance_score")
```

## Modules
| file | role |
|---|---|
| `registry.py` | stable KPI keys, formulas, units, limitations, compute spec (single source of truth) |
| `datasets.py` | dataset specs + provenance, canonical schema, duplicate / unit / missingness handling |
| `engine.py` | `compute`, `compute_grouped`, `trend`, target evaluation, `check_comparability` |
| `contract.py` | `KPIResult`, `TrendResult`, `TargetSpec`, `EvidenceType` (**proposed** shared contract) |

## Rules the engine enforces
1. Ratio of sums (`math.fsum`, order independent). Never an average of ratios.
2. Invalid / missing rows leave numerator **and** denominator; counted in `exclusion_reasons`; nothing imputed.
3. `value` is `null` (never 0 / inf) unless `status == "ok"`.
4. Unit problems (percent column that looks like a fraction, mixed currency) give `invalid_units`, no silent rescaling.
5. Targets only with a source; otherwise `target.status == "no_target_defined"`.
6. Cross-dataset comparison is refused unless data source, population, grain and period are compatible.
