# Metric definitions and integration contract

## Sources

Six synthetic company CSVs are authoritative. Public benchmark employee IDs are never joined to company IDs. Process datasets, supporting workbooks and policy documents are not loaded or changed. SCHEMA.md lists exact source columns and row counts.

## Calculations

- Headcount: unique retained nonempty employee IDs, including On Leave. Active means exact status `Active`. Distribution percentages divide by selected retained headcount and include Unknown categories.
- Tenure: mean of valid nonnegative tenure_months. Buckets <12, 12–<36, 36–<60 and >=60 months. New employee proxy is tenure <3 months; no hire date or workforce snapshot date exists.
- Engagement: job_satisfaction_1_to_5 is the headline metric, consistent with the supplied W02 mapping. All four 1–5 dimensions also have means and valid sample sizes. Low/high descriptive bands are <=2 / >=4 on the explicit scale. No invented composite. Intent to stay is not realized attrition.
- Skills: Beginner=1, Intermediate=2, Advanced=3. Required-for-role skills below Intermediate are gaps, consistent with the supplied W05 mapping. Denominator is required records with recognized proficiency. Unknown required levels remain separately visible. Department/skill tables expose counts and percentages. There is no catalog to infer unrecorded required skills.
- Workload: preserve actual, planned and reported overtime. Derived excess over plan=max(actual−planned,0) when both exist. Capacity=weekly_capacity_hours×inclusive period days/7. Utilization=100×sum(paired actual)/sum(corresponding positive capacity). Missing/zero capacity yields null. >100% overloaded; <80% underutilized; 80–100% balanced. The 80% band is an MVP convention, not documented company policy. Actual/planned percentages and utilization range describe workload patterns.
- Actual>planned with reported overtime=0 is flagged for definition review. It is not proof of incorrect payroll: planned hours may be below contractual capacity.
- KPI: mean valid performance_score by employee, department and month. The maximum scale is undocumented; scores are not percentages. First-to-last point changes use the observed months. Trends are not matched-cohort estimates; missing employees may affect composition. Other numeric KPI dimensions have their own valid sample counts.
- Means/differences use 2 decimals, percentages 1 decimal. Missing numbers are not imputed. Null means unavailable, not zero.

## Findings

Each finding contains id, category, severity, polarity, title, finding, metric, value, benchmark, difference, unit, affected_group, sample_size, confidence, evidence and data_quality. Evidence carries source filename, value, baseline, sample size and filters. Metadata includes source date ranges. IDs are deterministic for the same report, not globally persistent IDs.

Department engagement/KPI deviations trigger at >=10% relative difference from the selected population mean with at least five distinct employees. Smaller groups receive low-confidence observations. High/low engagement bands also produce findings. Workload >120% receives high severity; other band exceptions medium. Skill gap >=30% receives high severity; smaller gaps medium; zero assessable gaps produces an informational positive finding. First-to-last KPI changes >=10% with at least five employees at both endpoints produce trend findings. Validation warnings appear in the insight feed as well as the quality endpoint. These are descriptive heuristics, not statistical significance tests or causal claims. Confidence is at most medium for synthetic data.

Department filtering narrows the comparison population. Use an unfiltered response for company-wide comparisons.

## Validation and denominators

Missing/unreadable files, required columns, missing values, unknown proficiency/requirement labels, nonfinite/negative numerics, engagement outside 1–5, attendance above 100%, invalid ISO dates, reversed workload periods, missing IDs, unmatched employee IDs, department inconsistencies and overtime observations generate warnings.

Duplicate natural keys retain the first row with a warning: employee ID; department ID; employee+skill; employee+survey month; employee+workload period; employee+KPI month. Duplicate explicit survey/workload/KPI record IDs are also excluded. No source file is rewritten.

Invalid identity or keyed dates exclude a record. Invalid numeric cells become null and are excluded from their individual metric denominator. Unknown proficiency stays visible but is excluded from assessable requirements. Invalid skill assessment dates stay flagged and are excluded by date filters. Reversed workload periods prevent utilization derivation. Blank manager IDs are allowed for heads; unknown nonblank manager IDs are flagged.

Warnings contain type, severity, source, field, code, message, affected_rows, and up to 20 CSV row-number examples. Header is row 1; source/column-level observations use row 0. Multiple warning groups may overlap, so their sum is not a unique bad-record count.

## Limitations

Engagement has one survey month; workload has one weekly period. No longitudinal engagement trend or realized attrition rate can be inferred. No historical department assignment table or missing-skill catalog is available. The service is intended for trusted local use until platform authentication and authorization are connected.

## Backend validation refinements

Missing required text columns are materialized as empty values in the in-memory records, with warnings; an absent department-name column cannot crash the report. Source month fields require YYYY-MM and source day fields require YYYY-MM-DD, matching the inspected CSV schemas. Query date filters still accept either form.

Workload responses include `planned_actual_comparison` at organization and department levels. Its actual/planned totals, signed difference and percentage use only records where both values are valid. `sample_size` is the paired denominator; standalone totals retain their own `actual_hours_sample_size` and `planned_hours_sample_size`. A zero planned total produces a null ratio.

Metric insight evidence includes the metric identifier and observed source date range. Data-quality evidence includes example CSV row numbers and its explicitly unfiltered warning scope. Existing response fields and API routes are preserved.
