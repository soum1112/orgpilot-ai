# HUL Process Event Log (SYNTHETIC) - OrgPilot AI, Member 2

**Everything in this folder is synthetic.** No real HUL process data exists publicly. Activities, responsible teams,
timing windows and SLAs come from the four O2V SOPs (HR-TAL-001, HR-TAL-002, SCM-ECO-001, SCM-ECO-002); every case,
timestamp and delay is generated.

## Files
| File | Purpose |
|---|---|
| `process_event_log.csv` | Main input: 29,241 event rows, 3,300 cases, 6 case types across 4 processes |
| `process_targets.csv` | Targets taken from the SOP text, with a `comparable` flag (yes / approximate / no) |
| `process_expected_sequences.csv` | Expected activity order per case type, with optional steps flagged (for sequence-anomaly checks) |
| `process_injected_issues.csv` | Answer key listing every deliberately injected data defect. Use it to TEST your detectors; do not load it as input data |
| `generate_process_event_log.py` | Regenerates everything (fixed seed 2026) |

## Event log columns
`event_id`, `case_id`, `process_id`, `case_type`, `activity`, `status` (started / completed), `timestamp`
(ISO 8601, IST +05:30 unless noted below), `team`, `location`, `location_type` (site = plant/office city, state = Shakti rural state).

## How metrics map to the log
- Wait time = `started` of an activity minus `completed` of the previous activity.
- Stage elapsed time (`stage_elapsed_hours`) = `completed` of an activity minus `completed` of the previous activity.
- Case cycle time = last event minus first event of a case.
- Handoff delay = wait time where the `team` differs from the previous activity's team.

## Targets
`comparable = yes`: SOP gives a clear duration. `approximate`: SOP uses business days, a timing window, or a clock that starts
at a different event than the log measures (see `note`). `no`: SOP rule is not a duration. Only compare when `comparable` is yes
or approximate, and label approximate comparisons as such.

## Planted patterns (for demo; NOT real HUL findings)
- SCM-ECO-001: on-site audit is the slowest stage and its wait grows over 2024-2026; cases with an audit tend to exceed the 40-day cycle target.
- SCM-ECO-002: credit linkage often exceeds its window, worse in Jun-Sep; order delivery slows in Jun-Sep.
- HR-TAL-002: Interview & offer is slower at Orai, Sumerpur and Etah, and faster at Hosur.
- HR-TAL-001: CHRO review tends to exceed the 3-business-day SLA.
Treat any such pattern as a signal to investigate, never as a proven cause.

## Injected data-quality issues (answer key: `process_injected_issues.csv`)
Counts: {'duplicate_event': 432, 'rework_repeated_activity': 210, 'missing_timestamp': 201, 'out_of_order_sequence': 159, 'utc_timestamp_format': 144, 'invalid_timestamp': 86, 'abandoned_case': 72, 'in_progress_at_cutoff': 56, 'missing_activity': 38, 'negative_duration': 17}
- `in_progress_at_cutoff` and `rework_repeated_activity` are informational, not defects.
- Data cutoff (extraction date): 2026-09-30. Cases started after ~2026-09-20 may be open.
- `utc_timestamp_format` rows are valid instants written with a Z suffix. Parse with a timezone-aware parser.
- Duplicates have a different `event_id` but identical case, activity, status and timestamp.
- On-site audit is legitimately skipped in about 65% of vendor cases (optional), so absence there is not an anomaly.

## Limitations
Case IDs are independent of the Talent/Ecosystem master data (no employee/vendor IDs are linked). Weekends and holidays are not modelled.
