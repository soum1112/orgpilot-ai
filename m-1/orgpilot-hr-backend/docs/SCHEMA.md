# Actual CSV schemas

IDs/labels are strings. ISO months/dates are parsed as dates. The explicit numeric allowlist in analytics.py is parsed as finite nonnegative floats.

## departments.csv

10 records.

`department_id`, `department_name`, `data_source`

## employee_engagement_synthetic.csv

126 records.

`survey_id`, `employee_id`, `survey_month`, `job_satisfaction_1_to_5`, `manager_support_1_to_5`, `work_life_balance_1_to_5`, `growth_opportunity_1_to_5`, `intent_to_stay_6_months`, `survey_response`, `data_source`

## employee_kpi_monthly.csv

1134 records.

`kpi_record_id`, `employee_id`, `department_id`, `job_role`, `month`, `monthly_hours_worked`, `attendance_rate`, `training_hours`, `peer_review_score`, `manager_rating`, `performance_score`, `tasks_completed`, `Task_per_100h`, `data_source`

## employee_skills_synthetic.csv

504 records.

`employee_id`, `skill_name`, `proficiency_level`, `required_for_role`, `last_assessed_date`, `assessment_method`, `data_origin`, `data_source`

## employee_workforce_synthetic.csv

126 records.

`employee_id`, `employee_name`, `department_code`, `department`, `job_role`, `manager_id`, `employment_type`, `tenure_months`, `work_location`, `weekly_capacity_hours`, `employment_status`, `data_origin`, `data_source`

## employee_workload_synthetic.csv

126 records.

`record_id`, `employee_id`, `period_start`, `period_end`, `planned_hours`, `actual_hours`, `meeting_hours`, `focus_hours`, `open_work_items`, `completed_work_items`, `overtime_hours`, `data_origin`, `data_source`

