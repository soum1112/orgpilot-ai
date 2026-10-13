"""Turn every module's output into ONE shared finding shape.

Shared finding (superset of the team PDF's contract):
    finding_id, domain, category, title, metric, actual_value, target_value, benchmark_value, unit,
    severity (high|medium|low|info), scope{period, population}, evidence[{source_file, description,
    record_ids}], limitations[], data_source, retrieval_hints{process_id, keywords}

The modules are called as Python functions (no HTTP), and their numbers are passed through unchanged:
this layer never recalculates a metric.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

SEVERITIES = ("high", "medium", "low", "info")
SYNTHETIC = "synthetic demo data"
PUBLIC = "public benchmark data"
_PROCESS_ID = re.compile(r"\b([A-Z]{2,4}-[A-Z]{2,4}-\d{3})\b")

# Informational business KPIs surfaced as findings (observed values, no targets are invented).
KPI_SELECTION = [
    ("marketing.roas", "marketing_daily"),
    ("procurement.defect_rate_pct", "procurement_po"),
    ("procurement.avg_lead_time_days", "procurement_po"),
    ("performance.avg_performance_score", "employee_kpi_synthetic"),
]

_cache: dict[str, tuple[float, Any]] = {}
CACHE_SECONDS = 60


def clear_cache() -> None:
    _cache.clear()


def _cached(name: str, fn):
    now = time.time()
    hit = _cache.get(name)
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    value = fn()
    _cache[name] = (now, value)
    return value


def _num(v: Any) -> Any:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


# ----------------------------------------------------------------------------------------- HR (Member 1)
def _hr_one(i: dict[str, Any]) -> dict[str, Any]:
    ev = (i.get("evidence") or [{}])[0]
    windows = [f"{k}: {v.get('start')} to {v.get('end')}" for k, v in (ev.get("time_window") or {}).items()
               if isinstance(v, dict) and v.get("start")]
    n = i.get("sample_size")
    category = i.get("category")
    severity = i.get("severity") if i.get("severity") in SEVERITIES else "info"
    limitations = ["Shows an association in the data; it does not establish a cause",
                   f"{SYNTHETIC.capitalize()}: values illustrate the method, not a real company"]
    if isinstance(n, (int, float)) and n < 10:
        limitations.append(f"Small group (n={n}); treat as a weak signal")
    if i.get("confidence"):
        limitations.append(f"HR module confidence: {i['confidence']}")
    for code in i.get("data_quality") or []:
        limitations.append(f"Data-quality flag on the source file: {code}")
    description = f"{i.get('finding', '')} Sample size {n}."
    if category == "data_quality":
        severity = "info"
    return {
        "finding_id": i["id"],
        "domain": "hr",
        "category": category,
        "title": f"{i.get('affected_group')}: {i.get('title')}",
        "metric": i.get("metric"),
        "actual_value": _num(i.get("value")),
        "target_value": None,
        "benchmark_value": _num(i.get("benchmark")),
        "unit": i.get("unit"),
        "severity": severity,
        "scope": {"period": "; ".join(windows) or "dataset-defined period",
                  "population": f"{i.get('affected_group')} (n={n})"},
        "evidence": [{"source_file": ev.get("source"), "description": description, "record_ids": []}],
        "limitations": limitations,
        "data_source": SYNTHETIC,
        "retrieval_hints": {
            "process_id": None,
            "keywords": [str(category or ""), str(i.get("affected_group") or ""), str(i.get("title") or "")],
        },
    }


def hr_findings() -> list[dict[str, Any]]:
    from hr.analytics import HRAnalytics

    report = HRAnalytics(settings.HR_DATA_DIR, {}).report()
    return [_hr_one(i) for i in report["insights"]]


# ------------------------------------------------------------------------------------ Process (Member 2)
def _process_one(f: dict[str, Any]) -> dict[str, Any]:
    population = (f.get("scope") or {}).get("population", "")
    match = _PROCESS_ID.search(population) or _PROCESS_ID.search(f.get("title", ""))
    activity = re.split(r"\s\(", f.get("title", ""), maxsplit=1)[0]
    out = dict(f)
    out.setdefault("category", "process")
    out["benchmark_value"] = None
    out["data_source"] = SYNTHETIC
    out["retrieval_hints"] = {"process_id": match.group(1) if match else None,
                              "keywords": [activity, f.get("metric", "")]}
    return out


def process_findings() -> list[dict[str, Any]]:
    from process_api.views import analytics

    return [_process_one(f) for f in analytics().findings()]


# ---------------------------------------------------------------------------------------- KPI (Member 3)
def kpi_findings() -> list[dict[str, Any]]:
    from kpi_engine import KPIEngine

    engine = KPIEngine(data_dir=settings.KPI_DATA_DIR)
    out = []
    for n, (key, dataset) in enumerate(KPI_SELECTION, start=1):
        r = engine.compute(key, dataset).to_dict()
        if r["status"] != "ok":
            continue
        period = r.get("period") or {}
        public = r["data_source"] == PUBLIC
        limitations = list(r.get("warnings") or [])
        limitations.append("Observed value only; no target is defined for this KPI")
        if public:
            limitations.append("Public benchmark data from another organisation; not this company's performance")
        else:
            limitations.append(f"{SYNTHETIC.capitalize()}: values illustrate the method")
        out.append({
            "finding_id": f"KPI-{n:03d}",
            "domain": "business",
            "category": "kpi",
            "title": f"{r['display_name']} ({dataset})",
            "metric": key,
            "actual_value": _num(r["value"]),
            "target_value": None,
            "benchmark_value": None,
            "unit": r["unit_label"],
            "severity": "info",
            "scope": {"period": f"{period.get('start')} to {period.get('end')}",
                      "population": f"{dataset}; {r['n_rows_used']} valid rows"},
            "evidence": [{"source_file": r.get("dataset_id"),
                          "description": f"{r['display_name']} = {r['value']} ({r['unit_label']}) over "
                                         f"{r['n_rows_used']} valid rows; {r['n_rows_excluded']} rows excluded.",
                          "record_ids": []}],
            "limitations": limitations,
            "data_source": r["data_source"],
            "retrieval_hints": {"process_id": None, "keywords": [r["display_name"], key]},
        })
    return out


# --------------------------------------------------------------------------------------------- combined
MODULES = {"hr": hr_findings, "process": process_findings, "business": kpi_findings}
_SEV_ORDER = {s: i for i, s in enumerate(SEVERITIES)}


def collect_findings() -> dict[str, Any]:
    """All findings from every module. A module that fails is reported in `warnings`, never fatal."""
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    status: dict[str, str] = {}
    for name, fn in MODULES.items():
        try:
            findings.extend(_cached(name, fn))
            status[name] = "ok"
        except Exception as exc:  # noqa: BLE001 - one broken module must not take the others down
            logger.exception("module %s failed", name)
            status[name] = f"error: {exc}"
            warnings.append(f"Module '{name}' is unavailable: {exc}")
    findings.sort(key=lambda f: (_SEV_ORDER.get(f["severity"], 9), f["finding_id"]))
    sources = sorted({e.get("source_file") for f in findings for e in f["evidence"] if e.get("source_file")})
    return {"findings": findings, "warnings": warnings, "modules": status, "source_files": sources}


def get_finding(finding_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    bundle = collect_findings()
    for f in bundle["findings"]:
        if f["finding_id"] == finding_id:
            return f, bundle
    return None, bundle
