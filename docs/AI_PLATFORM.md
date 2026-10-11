# Shared backend + AI layer (Member 4)

One Django project (`backend/orgpilot_platform`) mounts every module without copying anyone's code:

| URL | Module | Owner |
|---|---|---|
| `/api/hr/...` | `m-1/orgpilot-hr-backend/backend/hr` | Member 1 |
| `/api/process/...` | `m-2/api/process_api` | Member 2 |
| KPI engine (Python library, used by the AI layer) | `backend/kpi_engine` | Member 3 |
| `/api/ai/...` | `backend/ai_insights` | Member 4 |

## Run it (from the repo root)
```
pip install -r requirements-platform.txt
python backend/manage.py runserver 8000
```
Open http://127.0.0.1:8000/api/ai/health/ . Tests: `python backend/manage.py test ai_insights`.

## Endpoints
| Method | Path | What it does |
|---|---|---|
| GET | `/api/ai/health/` | Model status, policy index size, module status |
| GET | `/api/ai/findings/` | All findings from HR, Process and KPI in ONE shape. Filters: `?domain=hr\|process\|business`, `?severity=high` |
| POST | `/api/ai/analyze/` | `{"finding_id": "PROC-001", "question": "optional", "use_llm": true}` -> plain-words explanation + policy excerpts |
| POST | `/api/ai/recommendations/` | Same input -> 2-3 proposed actions with risks, hypothesis-style benefit, citations |

Response envelope: `{status, data{..., generated_at}, meta{source_files, warnings}}`.
Key fields in `data`: `mode` (`llm` or `fallback`), `summary`, `key_points`, `recommendations`, `limitations`,
`policy_excerpts` (file + section + chunk id), `human_review_required` (always true), `llm.status`.

## The shared finding shape
`finding_id, domain, category, title, metric, actual_value, target_value, benchmark_value, unit, severity (high|medium|low|info),
scope{period, population}, evidence[{source_file, description, record_ids}], limitations[], data_source, retrieval_hints`.
`target_value` is only ever a documented target. HR's comparison values are `benchmark_value` (population average or threshold).

## Rules enforced in code
1. The model never receives raw data and never calculates. It gets one finding that Python already validated.
2. Output is rejected (one retry, then template fallback) if it contains a number that is not in the finding or the retrieved
   policy text, states a cause as fact, is not the expected JSON, or has no recommendations when asked for them.
3. Citations the model made up are removed; only retrieved chunk ids can be cited.
4. If Ollama is off, slow or broken the endpoints still answer (`mode: "fallback"`).
5. `human_review_required` is set by the server.

## Local model (optional)
```
ollama pull qwen2.5:7b-instruct
ollama serve
```
Check `/api/ai/health/` shows `reachable: true` and `model_available: true`. Use `use_llm=false` to skip the model.

## Policy documents
`.docx` and `.pdf` files in `OrgPilot_Dataset_Final/final/documents` and `m-2/docs/sops` are indexed automatically
(change with `POLICY_DOC_DIRS`). Process findings are matched to their own SOP by process id (e.g. HR-TAL-001).
