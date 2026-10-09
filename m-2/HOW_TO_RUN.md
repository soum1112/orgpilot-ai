# Member 2 - Process Intelligence: how to run

Needs Python 3 and Node.js (https://nodejs.org, "LTS" version) installed. Everything lives in the `m-2` folder.
The API reads `process_kpis.py` and the CSV files that sit in `m-2` (one level above `api/`).

## 1. Start the API (terminal 1)
```
cd m-2/api
pip install django djangorestframework pandas numpy
python manage.py runserver 8000
```
Check: open http://127.0.0.1:8000/api/process/overview/ - you should see JSON.

## 2. Start the dashboard (terminal 2)
```
cd m-2/dashboard
npm install
npm run dev
```
Open http://localhost:5173. Keep both terminals running.

## Tests
```
cd m-2/api && python manage.py test        # API tests
cd m-2 && python -m pytest -q              # KPI calculation tests (pip install pytest)
```

## Endpoints
GET /api/process/overview/ (overview + findings), /stages/, /bottlenecks/, /anomalies/
Response shape: {status, data{..., generated_at}, meta{source_files, warnings}}. Findings follow the team's shared contract.
