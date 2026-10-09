# Process Intelligence - KPI Definitions (Member 2)

All numbers are calculated in Python (`process_kpis.py`). The AI layer only explains them.
Source file: `data/process_event_log.csv` (synthetic). Targets: `process_targets.csv`. Expected order: `process_expected_sequences.csv`.

## Data preparation rules (applied before any KPI)
| Rule | What happens | Where it is reported |
|---|---|---|
| Missing timestamp (blank) | Row excluded | `meta.warnings`, `data_quality.missing_timestamp` |
| Unparseable timestamp (e.g. "N/A", "31-02-2025") | Row excluded | `data_quality.invalid_timestamp` |
| Timezones | All timestamps parsed as ISO 8601 and converted to UTC (`Z` and `+05:30` are the same instant) | - |
| Exact duplicate (same case, activity, status, timestamp) | Keep one | `data_quality.duplicate_events_removed` |
| Status other than started / completed | Row excluded | `data_quality.unknown_status_rows` |
| Negative duration (wait, processing or elapsed < 0) | That stage measurement excluded from averages, flagged | `data_quality.negative_duration_stages` |
| Out-of-order case (activities not in expected order) | Case excluded from stage timing statistics, still listed under anomalies | `data_quality.out_of_order_cases_excluded_from_timing` |

## KPIs
| Key | Definition / formula | Source columns | Unit | Grain |
|---|---|---|---|---|
| `completion_rate` | completed cases / cases whose expected sequence is known. A case is completed when its **last mandatory step** has a `completed` event | case_id, activity, status + expected sequences | ratio 0-1 | process / case type / overall |
| `cycle_time_hours` | last event timestamp - first event timestamp, **completed cases only** | case_id, timestamp | hours | case |
| `wait_time_hours` | first `started` of activity - first `completed` of previous activity | timestamp, status | hours | stage in a case |
| `processing_time_hours` | first `completed` - first `started` of the same activity | timestamp, status | hours | stage in a case |
| `stage_elapsed_hours` | first `completed` of activity - first `completed` of previous activity (= wait + processing) | timestamp, status | hours | stage in a case |
| `handoff_wait_hours` | wait time where `team` differs from the previous activity's team | team + above | hours | stage |
| `breach_rate` | stages with `stage_elapsed_hours` > target / stages with a valid measurement (strictly greater) | + targets file | ratio 0-1 | stage |
| `rework_rate` | cases where an activity has more than one `completed` event / cases that reached the activity | activity, status | ratio 0-1 | stage |
| `case_cycle_breach_rate` | completed cases with cycle time > case target / completed cases; also split by optional steps (e.g. with / without on-site audit) | + targets file | ratio 0-1 | process |

Stages are ordered by first `started` time within a case. For repeated activities (rework) the **first** occurrence is measured and the repeat is counted as rework.

## Anomalies
| Anomaly | Rule |
|---|---|
| Out-of-order sequence | The step numbers (from the expected-sequence file) of a case's activities, in time order, are not non-decreasing |
| Skipped mandatory step | A mandatory step with a lower step number than the furthest step reached has no events (optional steps and cases still in progress are never flagged) |
| Negative duration | Completed before started, or a step starting before the previous one completed |
| Stalled / abandoned | Case not completed and no event for more than 45 days before the latest event in the data |
| In progress | Case not completed, last event within 45 days of the latest event |
| Rework | Same activity completed more than once in a case (legitimate repeat, informational) |

## Targets: when they may be compared
`comparable = yes`: SOP gives a clear duration. `approximate`: business days, a derived window, or a different clock start (compared but labelled approximate). `no`: not a duration, never compared. A stage with no comparable target is `unrated`.

## Severity (stage bottlenecks)
- **high**: breach_rate >= 50% **and** mean elapsed > target
- **medium**: breach_rate >= 35% **or** mean elapsed > target
- **low**: otherwise
- **unrated**: no comparable target
- Stages need at least 20 valid measurements to be rated. Findings are produced for high and medium only.

## Limitations (state these in the demo)
- Data is synthetic. Delays are patterns to investigate, never proven causes.
- Approximate targets (business days, derived windows) are not exact SLAs.
- "Stalled/abandoned" can include cases whose final events had unusable timestamps.
- Segment differences (e.g. with vs without on-site audit) are associations, not causation.
- Weekends and holidays are not modelled.

## Shared finding format
Each finding has: `finding_id`, `domain` ("process"), `title`, `metric`, `actual_value`, `target_value`, `unit`, `severity`, `scope{period, population}`, `evidence[{source_file, description, record_ids}]`, `limitations[]` (the contract in the team PDF). API responses use `{status, data{..., generated_at}, meta{source_files, warnings}}`.

## Mapping to the planned endpoints
| Endpoint | Method |
|---|---|
| `GET /api/process/overview/` | `pa.envelope({"overview": pa.overview(), "findings": pa.findings()})` |
| `GET /api/process/stages/` | `pa.envelope({"stages": pa.stages_summary()})` |
| `GET /api/process/bottlenecks/` | `pa.envelope({"bottlenecks": pa.bottlenecks()})` |
| `GET /api/process/anomalies/` | `pa.envelope({"anomalies": pa.anomalies()})` |

## How to run
```
pip install pandas numpy pytest
cd m-2/analytics
python -m pytest -q                 # 18 unit tests
python process_kpis.py              # prints summary and top findings (reads ../data)
python validate_detectors.py        # checks detectors against the answer key
```
