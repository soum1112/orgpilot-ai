# OrgPilot AI - Unified Schema (FINAL)

Prepared by Member 4 for Timeless Software Pvt. Ltd. (fictional). Matches the files in `final/`.
Every table carries a `data_source` column: `public benchmark data` or `synthetic demo data`.

## A. Company tables (synthetic demo data)

| Table | File | Primary key | Links to |
|---|---|---|---|
| departments | synthetic/departments.csv | department_id | - |
| employees | synthetic/employee_workforce_synthetic.csv (126 rows) | employee_id | departments.department_id (via department_code); employees.employee_id (via manager_id) |
| employee_skills | synthetic/employee_skills_synthetic.csv (504 rows, 4 per employee) | employee_id + skill_name | employees |
| employee_engagement | synthetic/employee_engagement_synthetic.csv (126 rows) | survey_id | employees |
| employee_workload | synthetic/employee_workload_synthetic.csv (126 rows) | record_id | employees |
| employee_kpi_monthly | synthetic/employee_kpi_monthly.csv (1,134 rows) | kpi_record_id (unique per employee_id + month) | employees |
| resources | synthetic/resources.csv (6 rows) | resource_id | departments |
| process_events | synthetic/process_event_log_synthetic.csv (4,496 rows) | case_id + activity + timestamp | resources (resource = resource_name) |
| process_case_summary | synthetic/process_kpi_case_summary.csv (600 rows) | case_id | process_events |
| process KPI tables | process_kpi_by_outcome, process_kpi_handoffs, process_kpi_step_wait_times, process_kpi_monthly_cycle_time | - | derived from process_events |

## B. Public benchmark tables (not joined at employee level)

| File | Use |
|---|---|
| ibm_hr_analytics_attrition.csv (EmployeeNumber) | Attrition and satisfaction benchmark |
| employee_kpi_records, employee_kpi_by_department, employee_kpi_by_month | Reference ranges for employee KPIs |
| marketing_kpi_by_campaign, marketing_kpi_daily | Marketing KPIs |
| procurement_kpi_po_level, procurement_kpi_by_supplier, procurement_kpi_by_quarter | Procurement KPIs |

Public files link to the company only at department level through `department_map`.

## C. Mapping tables (mappings/)

| File | Purpose |
|---|---|
| department_map.csv | Public-file department names to department_id (HR to HR, IT to ENG, Sales to SAL, and so on) |
| resource_map.csv | Process teams to resource_id and department_id (Dev Team to ENG, QA Team to QA, Security Team to SEC, Service Desk to SUP, Engineering Manager to ENG, Requester has no department) |
| kpi_column_map.csv | 20 KPIs: formula, unit, source file, source columns, label |

## D. Departments (10)

ENG Engineering, QA Quality Assurance, OPS Operations, SUP Customer Support, PMO Product & Project Management, HR People Operations, SEC Security, SAL Sales, FIN Finance, MKT Marketing. Each has one head (an employee with no manager) and its own employees.

## E. Gaps found and how each was closed

| Gap | Resolution |
|---|---|
| Process log had no employee or department link | Linked at team level through resources.csv and resource_map.csv |
| Sales, Finance, Marketing and Security had no departments or staff | Added to departments.csv; 26 synthetic employees (EMP0101 to EMP0126) with skills, engagement and workload records |
| Member 3's employee IDs (E1000...) differed from EMP IDs and are public records | Not mapped. Synthetic employee_kpi_monthly generated for the EMP IDs, using value ranges from the public file |
| Three different department lists | One master list (departments.csv) plus department_map.csv |
| Process data dated 2024, HR data 2026 | Process dates shifted by +2 years; all synthetic data now in 2026-01 to 2026-09 |
| Source links and licenses for Member 3's files | OPEN: Member 3 to supply exact URL and license for each file |

## F. Validation

`final/integration_checklist.md` lists every check (files, labels, IDs, relationships, types, dates, process data, KPI map, documents).
