# Member 2 - Process Intelligence

## Folder map
| Folder | What is inside |
|---|---|
| `data/` | Synthetic process event log, targets, expected sequences, answer key, generator script |
| `analytics/` | `process_kpis.py` (all calculations), tests, detector validation |
| `api/` | Django REST API (4 endpoints) that serves the analytics |
| `dashboard/` | React dashboard that displays the API results |
| `docs/` | `KPI_DEFINITIONS.md` and `sops/` (the 4 SOP Word documents the process data is based on) |

## How to run
Needs Python 3 and Node.js (https://nodejs.org, LTS version).

**Terminal 1 - API**
```
cd m-2/api
pip install django djangorestframework pandas numpy
python manage.py runserver 8000
```
Check in a browser: http://127.0.0.1:8000/api/process/overview/

**Terminal 2 - dashboard**
```
cd m-2/dashboard
npm install
npm run dev
```
Open http://localhost:5173 (keep both terminals running).

## Tests
```
cd m-2/api && python manage.py test          # API tests
cd m-2/analytics && python -m pytest -q      # calculation tests (pip install pytest)
```

## Endpoints
GET /api/process/overview/ (overview + findings), /stages/, /bottlenecks/, /anomalies/
Response shape: {status, data{..., generated_at}, meta{source_files, warnings}}. Findings follow the team's shared contract.
