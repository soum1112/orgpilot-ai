# OrgPilot AI - Integration Checklist

Generated: 2026-10-05 01:28  
Result: **143 passed, 1 warnings, 0 failed**


## 1. Folder structure and files

| Status | Check | Detail |
|---|---|---|
| PASS | final/public_benchmark exists |  |
| PASS | final/public_benchmark: all 9 expected files present |  |
| PASS | final/synthetic exists |  |
| PASS | final/synthetic: all 13 expected files present |  |
| PASS | final/mappings exists |  |
| PASS | final/mappings: all 3 expected files present |  |
| PASS | final/documents exists |  |
| PASS | final/documents: all 3 expected files present |  |
| PASS | final/supporting has files | 9 files |

## 2. Data labels (public vs synthetic)

| Status | Check | Detail |
|---|---|---|
| PASS | public_benchmark/employee_kpi_by_department.csv labelled 'public benchmark data' |  |
| PASS | public_benchmark/employee_kpi_by_month.csv labelled 'public benchmark data' |  |
| PASS | public_benchmark/employee_kpi_records.csv labelled 'public benchmark data' |  |
| PASS | public_benchmark/ibm_hr_analytics_attrition.csv labelled 'public benchmark data' |  |
| PASS | public_benchmark/marketing_kpi_by_campaign.csv labelled 'public benchmark data' |  |
| PASS | public_benchmark/marketing_kpi_daily.csv labelled 'public benchmark data' |  |
| PASS | public_benchmark/procurement_kpi_by_quarter.csv labelled 'public benchmark data' |  |
| PASS | public_benchmark/procurement_kpi_by_supplier.csv labelled 'public benchmark data' |  |
| PASS | public_benchmark/procurement_kpi_po_level.csv labelled 'public benchmark data' |  |
| PASS | synthetic/departments.csv labelled 'synthetic demo data' |  |
| PASS | synthetic/employee_engagement_synthetic.csv labelled 'synthetic demo data' |  |
| PASS | synthetic/employee_kpi_monthly.csv labelled 'synthetic demo data' |  |
| PASS | synthetic/employee_skills_synthetic.csv labelled 'synthetic demo data' |  |
| PASS | synthetic/employee_workforce_synthetic.csv labelled 'synthetic demo data' |  |
| PASS | synthetic/employee_workload_synthetic.csv labelled 'synthetic demo data' |  |
| PASS | synthetic/process_event_log_synthetic.csv labelled 'synthetic demo data' |  |
| PASS | synthetic/process_kpi_by_outcome.csv labelled 'synthetic demo data' |  |
| PASS | synthetic/process_kpi_case_summary.csv labelled 'synthetic demo data' |  |
| PASS | synthetic/process_kpi_handoffs.csv labelled 'synthetic demo data' |  |
| PASS | synthetic/process_kpi_monthly_cycle_time.csv labelled 'synthetic demo data' |  |
| PASS | synthetic/process_kpi_step_wait_times.csv labelled 'synthetic demo data' |  |
| PASS | synthetic/resources.csv labelled 'synthetic demo data' |  |
| PASS | mappings/department_map.csv has a valid data_source |  |
| PASS | mappings/kpi_column_map.csv has a valid data_source |  |
| PASS | mappings/resource_map.csv has a valid data_source |  |

## 3. IDs and relationships

| Status | Check | Detail |
|---|---|---|
| PASS | departments: department_id is unique and never empty | 10 values |
| PASS | employees: employee_id is unique and never empty | 126 values |
| PASS | employees.department_code exists in departments | all found |
| PASS | every department has at least 1 employee | empty: [] |
| PASS | employees.manager_id exists in employees | all found |
| PASS | every employee's manager is in the same department |  |
| PASS | each department has exactly one head (employee with no manager) | 10 heads for 10 departments |
| PASS | department names in employees match departments.csv |  |
| PASS | skills.employee_id exists in employees | all found |
| PASS | every employee has at least one skill record |  |
| PASS | no duplicate (employee, skill) rows |  |
| PASS | engagement: survey_id is unique and never empty | 126 values |
| PASS | engagement.employee_id exists in employees | all found |
| PASS | every employee has an engagement record |  |
| PASS | workload: record_id is unique and never empty | 126 values |
| PASS | workload.employee_id exists in employees | all found |
| PASS | every employee has a workload record |  |
| PASS | employee_kpi_monthly: kpi_record_id is unique and never empty | 1134 values |
| PASS | employee_kpi_monthly.employee_id exists in employees | all found |
| PASS | employee_kpi_monthly: one row per employee per month |  |
| PASS | every employee has KPI rows for all months | months per employee: [np.int64(9)] |
| PASS | KPI rows carry the same department and job role as the employee |  |
| PASS | resources: resource_id is unique and never empty | 6 values |
| PASS | resources.department_id exists in departments | all found |
| PASS | resource_map matches resources.csv |  |
| PASS | no FILL_ME left in resource_map |  |
| PASS | department_map.department_id exists in departments | all found |

## 4. Data types and value ranges

| Status | Check | Detail |
|---|---|---|
| PASS | employees.tenure_months is numeric and positive |  |
| PASS | employees.weekly_capacity_hours is numeric and positive |  |
| PASS | employees: no empty name, role or department |  |
| PASS | engagement.job_satisfaction_1_to_5 is between 1 and 5 |  |
| PASS | engagement.manager_support_1_to_5 is between 1 and 5 |  |
| PASS | engagement.work_life_balance_1_to_5 is between 1 and 5 |  |
| PASS | engagement.growth_opportunity_1_to_5 is between 1 and 5 |  |
| PASS | workload.planned_hours is numeric and not negative |  |
| PASS | workload.actual_hours is numeric and not negative |  |
| PASS | workload.meeting_hours is numeric and not negative |  |
| PASS | workload.focus_hours is numeric and not negative |  |
| PASS | workload.open_work_items is numeric and not negative |  |
| PASS | workload.completed_work_items is numeric and not negative |  |
| PASS | workload.overtime_hours is numeric and not negative |  |
| PASS | employee_kpi_monthly has no missing values |  |
| PASS | attendance_rate is between 0 and 100 |  |
| PASS | employee_kpi_monthly.monthly_hours_worked is numeric and not negative |  |
| PASS | employee_kpi_monthly.tasks_completed is numeric and not negative |  |
| PASS | employee_kpi_monthly.training_hours is numeric and not negative |  |

## 5. Dates (agreed range 2026-01 to 2026-09)

| Status | Check | Detail |
|---|---|---|
| PASS | event log timestamps all parse as dates |  |
| PASS | event log timestamps inside 2026-01 to 2026-09 | 2026-01-01 11:27:15.546235104 to 2026-07-02 10:36:57.797294657 |
| PASS | case summary start parses and is inside 2026-01 to 2026-09 |  |
| PASS | case summary end parses and is inside 2026-01 to 2026-09 |  |
| PASS | employee_kpi_monthly months inside 2026-01 to 2026-09 | 2026-01 to 2026-09 |

## 6. Process data

| Status | Check | Detail |
|---|---|---|
| PASS | case IDs in event log and case summary are identical | 600 vs 600 cases |
| PASS | case summary: case_id is unique and never empty | 600 values |
| PASS | every event-log resource exists in resources.csv | all found |
| PASS | every case starts with 'Request Submitted' |  |
| WARN | cases that do not end with a 'Closed' step | 2 cases (likely the deliberate out-of-sequence cases in Member 2's data) |
| PASS | case outcomes are Completed / Rejected / Cancelled |  |
| PASS | process_kpi_by_outcome totals match the case summary | 600 vs 600 |

## 7. KPI column map

| Status | Check | Detail |
|---|---|---|
| PASS | kpi_column_map: kpi_id is unique and never empty | 20 values |
| PASS | W01 Attrition rate: source columns exist |  |
| PASS | W01: label matches its source file |  |
| PASS | W02 Average job satisfaction: source columns exist |  |
| PASS | W02: label matches its source file |  |
| PASS | W03 Overtime rate: source columns exist |  |
| PASS | W03: label matches its source file |  |
| PASS | W04 Workload utilization: source columns exist |  |
| PASS | W04: label matches its source file |  |
| PASS | W05 Skill gap rate: source columns exist |  |
| PASS | W05: label matches its source file |  |
| PASS | W06 Work item completion rate: source columns exist |  |
| PASS | W06: label matches its source file |  |
| PASS | P01 Average cycle time: source columns exist |  |
| PASS | P01: label matches its source file |  |
| PASS | P02 Step wait time: source columns exist |  |
| PASS | P02: label matches its source file |  |
| PASS | P03 Handoff rate: source columns exist |  |
| PASS | P03: label matches its source file |  |
| PASS | P04 Case completion rate: source columns exist |  |
| PASS | P04: label matches its source file |  |
| PASS | E01 Average performance score: source columns exist |  |
| PASS | E01: label matches its source file |  |
| PASS | E02 Average attendance rate: source columns exist |  |
| PASS | E02: label matches its source file |  |
| PASS | E03 Tasks per 100 hours: source columns exist |  |
| PASS | E03: label matches its source file |  |
| PASS | M01 Return on ad spend (ROAS): source columns exist |  |
| PASS | M01: label matches its source file |  |
| PASS | M02 Click-through rate (CTR): source columns exist |  |
| PASS | M02: label matches its source file |  |
| PASS | M03 Cost per order (CPO): source columns exist |  |
| PASS | M03: label matches its source file |  |
| PASS | R01 Procurement savings: source columns exist |  |
| PASS | R01: label matches its source file |  |
| PASS | R02 Average lead time: source columns exist |  |
| PASS | R02: label matches its source file |  |
| PASS | R03 Defect rate: source columns exist |  |
| PASS | R03: label matches its source file |  |
| PASS | R04 Compliance rate: source columns exist |  |
| PASS | R04: label matches its source file |  |

## 8. Documents

| Status | Check | Detail |
|---|---|---|
| PASS | Organization_Overview_ORG-001.docx opens and has text | 75589 characters |
| PASS | Operating_Policy_OPS-001.docx opens and has text | 12367 characters |
| PASS | Process_Guidelines_PRC-001.pdf is a valid PDF file |  |
| PASS | Organization_Overview_ORG-001.docx: no old company name |  |
| PASS | Operating_Policy_OPS-001.docx: no old company name |  |
| PASS | Process_Guidelines_PRC-001.pdf: no old company name |  |
| PASS | Organization Overview names every department head from the data |  |
| PASS | Organization Overview states the correct employee count | expects 126 |
| PASS | Organization Overview mentions every department |  |
| PASS | Process Guidelines covers every activity in the event log |  |
| PASS | Process Guidelines covers every team in the event log |  |