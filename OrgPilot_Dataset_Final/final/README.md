# OrgPilot AI - Dataset Folder

Data for the OrgPilot AI hackathon project (React + Django). The fictional company is **Timeless Software Pvt. Ltd.**, an IT/software company.

Every CSV has a `data_source` column:
- `public benchmark data` - real datasets from public sources (cleaned by the team)
- `synthetic demo data` - invented records

Validation result: see `integration_checklist.md` (143 checks passed, 1 expected warning, 0 failed).

## 1. Folder layout

```
final/
  public_benchmark/   public datasets (HR, employee KPIs, marketing, procurement)
  synthetic/          the fictional company: departments, employees, process log, KPIs
  mappings/           department_map, resource_map, kpi_column_map
  documents/          3 sample company documents (2 Word, 1 PDF)
  supporting/         charts, workbooks and scripts from Members 2 and 3
  README.md
  unified_schema.md
  integration_checklist.md
```

## 2. How the data connects

```
departments.csv (department_id)
   +-- employee_workforce_synthetic.csv (employee_id, department_code, manager_id)
         +-- employee_skills_synthetic.csv       (employee_id)
         +-- employee_engagement_synthetic.csv   (employee_id)
         +-- employee_workload_synthetic.csv     (employee_id)
         +-- employee_kpi_monthly.csv            (employee_id)
   +-- resources.csv (resource_id, department_id)
         +-- process_event_log_synthetic.csv     (resource = resource_name)
               +-- process_kpi_case_summary.csv  (case_id)
```

The public benchmark files are NOT joined to the company at employee level. They connect only at department level through `mappings/department_map.csv`.

## 3. What each dataset lets OrgPilot analyse

### synthetic/ (synthetic demo data)

| File | One row is | Analysis it enables |
|---|---|---|
| departments.csv | a department (10) | Organization structure |
| employee_workforce_synthetic.csv | an employee (126) | Departments, roles, reporting lines, span of control, reporting gaps |
| employee_skills_synthetic.csv | one skill of one employee (504) | Skill gaps (required skills below Intermediate) |
| employee_engagement_synthetic.csv | an employee survey response (126) | Satisfaction and engagement by department |
| employee_workload_synthetic.csv | an employee's weekly workload (126) | Utilization, overtime, open vs completed work |
| employee_kpi_monthly.csv | an employee in a month (1,134) | Performance, attendance, training and task KPIs by employee and department |
| resources.csv | a process team (6) | Links process steps to departments |
| process_event_log_synthetic.csv | one recorded step of a request (4,496) | Bottlenecks, waiting times, handoffs, out-of-sequence steps |
| process_kpi_case_summary.csv | a request (600) | Cycle time, handoffs, outcome per request |
| process_kpi_by_outcome.csv | an outcome (3) | Completed / rejected / cancelled share |
| process_kpi_handoffs.csv | handoff counts between teams | Handoff analysis |
| process_kpi_step_wait_times.csv | a step-to-step transition | Where requests wait longest |
| process_kpi_monthly_cycle_time.csv | a month | Cycle-time trend |

### public_benchmark/ (public benchmark data)

| File | One row is | Analysis it enables |
|---|---|---|
| ibm_hr_analytics_attrition.csv | an employee (1,470) | Attrition and satisfaction benchmark for workforce analysis |
| employee_kpi_records.csv | an employee in a month | Realistic ranges for employee performance KPIs |
| employee_kpi_by_department.csv, employee_kpi_by_month.csv | department / month summaries | Department and month comparisons |
| marketing_kpi_by_campaign.csv | a campaign | ROAS, click-through rate, cost per order |
| marketing_kpi_daily.csv | a campaign-day | Marketing trends over time |
| procurement_kpi_po_level.csv | a purchase order (777) | Savings, lead time, defect rate, compliance |
| procurement_kpi_by_supplier.csv, procurement_kpi_by_quarter.csv | supplier / quarter summaries | Supplier scorecard and quarterly trend |

### mappings/ and documents/

| File | Purpose |
|---|---|
| department_map.csv | Translates department names in the public files to company departments |
| resource_map.csv | Links each process team to a department |
| kpi_column_map.csv | 20 KPIs with formula, unit, source file, exact source columns and label |
| Organization_Overview_ORG-001.docx | Departments, heads, headcount, roles, reporting lines |
| Operating_Policy_OPS-001.docx | Company rules and targets |
| Process_Guidelines_PRC-001.pdf | IT access/change request steps, owners, target times |

## 4. Sources and licenses

| Data | Source | Status |
|---|---|---|
| ibm_hr_analytics_attrition.csv | https://www.kaggle.com/datasets/pavansubhasht/ibm-hr-analytics-attrition-dataset | Check the license on the Kaggle page before redistributing |
| Member 3's KPI files (employee, marketing, procurement) | Public sources such as Kaggle, cleaned by Member 3 | TO BE COMPLETED: exact URL and license for each file |
| Everything in `synthetic/` and `documents/` | Generated by the team | Synthetic demo data |

## 5. Changes made to the members' files

1. A `data_source` column was added to every CSV. Original files are untouched in the members' drives.
2. The process files were shifted forward by 2 years (2024 to 2026) so all synthetic data shares one period (2026-01 to 2026-09). Durations and order of steps are unchanged.
3. 26 synthetic employees (EMP0101 to EMP0126) were added to Security, Sales, Finance and Marketing, with linked skills, engagement and workload records. The original 100 employees are unchanged.
4. `employee_kpi_monthly.csv` was generated for all employees. Its value ranges were copied from the public `employee_kpi_records.csv`, but no public record is linked to any synthetic employee.
5. Customer Support was given slightly lower synthetic performance, manager rating and attendance on purpose, so there is a pattern to detect.
6. Member 3's public files were cleaned and had derived columns added (for example `Task_per_100h`).

## 6. Rules followed

- No datasets were joined by assuming IDs match.
- All invented records are labelled `synthetic demo data`; external data is labelled `public benchmark data`.
- KPI arithmetic is meant to be done with deterministic Python code (formulas in `mappings/kpi_column_map.csv`). The AI model explains validated results and proposes actions.

## 7. Built-in demo findings (for testing OrgPilot)

| Finding | Evidence |
|---|---|
| Manager approval is the bottleneck | Mean wait 30 hours against a 24-hour target (PRC-001) |
| Some requests break the sequence rules | 4 requests had steps out of order (for example implementation before security review) |
| Completion rate below target | 83.2% completed against an 85% target (OPS-001) |
| Customer Support has the lowest performance | Lowest average performance score of all departments |
| Flat reporting structure | Department heads have up to 16 direct reports, with no middle layer recorded |
| Some department heads have non-leadership titles | For example the Engineering head is recorded as a DevOps Engineer |
