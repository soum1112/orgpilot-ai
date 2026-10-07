# HR backend integration

The existing `hr.analytics.HRAnalytics` service implements workforce, department, engagement, workload, skills, KPI and deterministic insight analytics using Python's standard library. No Pandas/DRF dependency is needed for these small CSVs; existing Django JSON views are retained.

## Run and verify

From the project root, after installing requirements in your environment:

```sh
python backend/manage.py test hr
python backend/manage.py check
python backend/manage.py runserver 127.0.0.1:8000
```

Set `HR_DATA_DIR` to the directory containing the six company CSVs, or use the included default `data/synthetic`. This backend needs no database or migrations. Environment settings are read from the process; `.env` is not automatically loaded.

## Routes

GET `/api/hr/overview/`, `/api/hr/departments/`, `/api/hr/skills-gaps/`, `/api/hr/workload/`, `/api/hr/engagement/`, `/api/hr/kpis/`, `/api/hr/insights/`, `/api/hr/data-quality/`.

The existing aggregate `/api/hr/dashboard/` JSON endpoint remains for compatibility; no frontend work is part of this backend update.

Responses have `status`, `data`, `metadata`, and `warnings`. Invalid query filters produce 400, other methods 405; absent/malformed records produce partial results and structured warnings. Unexpected server errors are logged but not exposed.

## AI service

```python
from hr.analytics import get_hr_ai_context
context = get_hr_ai_context()  # uses configured Django HR_DATA_DIR
# Standalone Python:
context = get_hr_ai_context('/absolute/path/to/data/synthetic')
```

Includes key metrics, department comparisons, skill gaps, workload/engagement/KPI findings, source evidence, and quality warnings. The AI explains these values; it must not calculate them or make causal claims. No raw employee names are included.

See `docs/ANALYTICS.md` for thresholds, denominators, filter scopes and limitations; `docs/SCHEMA.md` contains inspected column names. Department differences are descriptive heuristics, not statistical significance tests. The source data is synthetic. This local backend has no authentication; reuse platform access controls before shared deployment.
