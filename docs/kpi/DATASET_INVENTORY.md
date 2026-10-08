# KPI dataset inventory (v0.1)

Scope: the four datasets behind the Business Performance / KPI Engine registry. Verified against
`OrgPilot_Dataset_Final.zip` (`final/`) on 2026-10-08 by `scripts/profile_datasets.py` and the test-suite
(`test_reconciliation.py`). Machine-readable column profiles: `dataset_inventory.json`.

## 1. The datasets do NOT share a company, population or period

| dataset_id | file (under `final/`) | data_source | what the rows describe | period | rows |
|---|---|---|---|---|---|
| `marketing_daily` | `public_benchmark/marketing_kpi_daily.csv` | public benchmark | 11 ad campaigns of an unnamed advertiser | **2021-02-01 to 2021-02-28** (one month) | 308 |
| `procurement_po` | `public_benchmark/procurement_kpi_po_level.csv` | public benchmark | 777 purchase orders, 5 suppliers, unnamed buyer | **order dates 2022-01-01 to 2024-01-01** | 777 |
| `employee_kpi_public` | `public_benchmark/employee_kpi_records.csv` | public benchmark | ids E1000 to E1099, unnamed employer | **2024-01 to 2024-11** (2024-02 absent) | 1,200 |
| `employee_kpi_synthetic` | `synthetic/employee_kpi_monthly.csv` | synthetic demo | 126 employees of the fictional Timeless Software Pvt. Ltd. | **2026-01 to 2026-09** | 1,134 |

Consequences enforced in code (`check_comparability`):

* No two datasets overlap in period, and none shares a population: **no cross-dataset comparison is valid.**
* Public vs synthetic employee KPIs are additionally *circular*: the README states the synthetic value ranges were copied
  from the public file (confirmed: min/max identical on 4 of 7 measure columns, and inside the public range on the other 3). Synthetic employees are not linked to any public id.
* Public benchmark and synthetic company records are never merged, and every result carries `dataset_id` + `data_source`.

Pre-aggregated files (`marketing_kpi_by_campaign`, `procurement_kpi_by_supplier`, `procurement_kpi_by_quarter`,
`employee_kpi_by_department`, `employee_kpi_by_month`) are **not inputs**. They are used only as reconciliation
oracles: the engine reproduces them from raw rows to relative tolerance 1e-9.

## 2. Per-dataset detail

### `marketing_daily`
* **Grain:** campaign x day. 11 campaigns x 28 days = 308, complete grid, no duplicate (date, campaign).
* **IDs:** `id` (row id), `campaign_id` (1 per campaign). Engine key: (date, lower-cased campaign).
* **Columns used:** `c_date`, `campaign_name`, `category` (4: influencer, media, search, social), `impressions`, `clicks`, `leads`, `orders` (int), `mark_spent`, `revenue` (float).
* **Units:** counts; `mark_spent` / `revenue` in an **unstated currency**. Revenue is gross.
* **Missingness:** none in raw columns. 19 days have 0 orders (revenue is 0 exactly then); 4 days have 0 leads.
* **Quality:** `facebOOK_tier2` casing inconsistency (engine lower-cases; equals the team's `campaign_name_clean`). Funnel valid in every row (clicks <= impressions, orders <= leads). Outliers: `banner_partner` up to 420M impressions/day; one `youtube_blogger` day with 880k spend.
* **Provenance:** original URL / licence **not supplied** (README section 4 "TO BE COMPLETED").

### `procurement_po`
* **Grain:** one purchase order. `PO_ID` unique (777).
* **Columns used:** `Order_Date`, `Delivery_Date`, `Supplier` (5), `Item_Category` (5), `Order_Status` (Delivered 560, Pending 81, Partially Delivered 73, Cancelled 63), `Quantity`, `Unit_Price`, `Negotiated_Price`, `Defective_Units`, `Compliance` (Yes/No).
* **Units:** quantity in units (mixed item types); prices in an **unstated currency**.
* **Missingness:** `Delivery_Date` 87 (68 of them on *Delivered* POs); `Defective_Units` 136 (102 on Delivered): likely data gaps, **not imputed**.
* **Quality:** 1 PO (`PO-00101`) delivered 5 days *before* it was ordered; Cancelled/Pending POs carry delivery dates (130 included in the lead-time sample); 2024Q1 holds only 2 POs (order dates end 2024-01-01); "Compliance" is undefined in the source.
* **Derived columns in the file are not used.** `PO_Value_*`, `Savings*`, `Lead_Time_*`, `Defect_Rate_Pct`, `Compliant_Flag` were verified to equal the raw arithmetic, but the engine recomputes from raw columns.
* **Provenance:** original URL / licence **not supplied**.

### `employee_kpi_public`
* **Grain (as documented):** employee x month. **Actual:** 1,200 rows, 100 ids, 12 rows per id over 10 months, so **200 employee-month keys appear twice (400 rows)** with different department / attributes (months 2024-01 and 2024-03). Not exact duplicates, so they cannot be de-duplicated; flagged `Dup_emp_month` in the file.
* **department is unstable per id** (3 to 5 departments each, about 4.6 on average). Department results are valid only at record level.
* **Columns used:** `employee_id`, `department` (5), `month`, `monthly_hours_worked`, `attendance_rate` (0 to 100), `tasks_completed`, `performance_score`, plus `training_hours` and `peer_review_score` (60 missing each; not used by v0.1 KPIs).
* **Units:** hours; percent; counts; `performance_score` **scale undocumented** (observed 0 to 30.89).
* **Signal:** a linear fit of performance_score on all other measures has R^2 of 0.027, so the score is not explained by recorded drivers; descriptive only.
* **Provenance:** original URL / licence **not supplied**.

### `employee_kpi_synthetic`
* **Grain:** employee x month, one row per pair (1,134 = 126 x 9), no duplicates, no missing values. `department_id` is stable and matches the roster.
* `Task_per_100h` is rounded to 2 dp in the file (up to 0.005 off); the engine recomputes from raw columns.
* Built-in demo pattern confirmed: Customer Support (SUP) has the lowest mean performance score (12.19).

## 3. Targets

`OPS-001` states numeric targets only for **process** KPIs (close within 3 days; at least 85% Completed), owned elsewhere.
It lists the employee review KPIs (section 6) **without numeric targets**. No document gives a target for any marketing,
procurement or employee-performance KPI, so none is registered and the engine returns `no_target_defined`.

## 4. Discrepancies found in the package (for the owners)

| # | Where | Finding | Owner / status |
|---|---|---|---|
| 1 | `mappings/kpi_column_map.csv` R03 | Literal formula `sum(Defective)/sum(Quantity)` gives 5.64%; the published supplier and quarter files use units-weighted over rows *with* defect data (6.80%). **Resolved in the registry** (`procurement.defect_rate_pct`), correct the map text. | Me |
| 2 | `kpi_column_map.csv` R01 | Lists derived `PO_Value_*` columns; engine uses raw `Quantity x price` (numerically identical, tested). | Me, FYI |
| 3 | `kpi_column_map.csv` E01 to E03 | Point only at the *public* file; the synthetic `employee_kpi_monthly.csv` has no map entry. Registry keys now cover both datasets as separate series. | Member 1 to confirm |
| 4 | README section 5 vs `integration_checklist.md` | README says all synthetic data covers 2026-01 to 2026-09, but the process event log runs 2026-01-01 to 2026-07-02 and the case summary covers 6 months (2026-01 to 2026-06). | Member 2 |
| 5 | README section 4 | Source URL / licence for the three public KPI files still open. | Me (cannot be derived from the files) |
| 6 | `department_map.csv` | Maps only 5 public department names; rows themselves are labelled "synthetic demo data". | Member 1 |
