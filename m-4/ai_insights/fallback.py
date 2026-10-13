"""Template answer used when the language model is offline or its output is rejected.

Everything here is built by code from the finding's own fields, so the app still works without a model.
"""
from __future__ import annotations

from typing import Any


def _fmt(v: Any) -> str:
    return f"{v:g}" if isinstance(v, float) else str(v)


def build(finding: dict[str, Any], excerpts: list[dict[str, Any]], task: str) -> dict[str, Any]:
    actual, target, bench = finding.get("actual_value"), finding.get("target_value"), finding.get("benchmark_value")
    unit = finding.get("unit") or ""
    title = finding.get("title", "Finding")

    if actual is not None and target is not None:
        gap = round(actual - target, 2)
        direction = "above" if gap > 0 else "below" if gap < 0 else "equal to"
        summary = (f"{title}. The measured value is {_fmt(actual)} {unit}, which is {_fmt(abs(gap))} {unit} "
                   f"{direction} the target of {_fmt(target)} {unit}." if gap else
                   f"{title}. The measured value ({_fmt(actual)} {unit}) equals the target.")
    elif actual is not None and bench is not None:
        summary = (f"{title}. The value is {_fmt(actual)} {unit}; the comparison value used by the analytics "
                   f"module is {_fmt(bench)} {unit}.")
    elif actual is not None:
        summary = f"{title}. The observed value is {_fmt(actual)} {unit}."
    else:
        summary = f"{title}. The analytics module did not produce a value for this finding."

    points = [f"Severity: {finding.get('severity')}",
              f"Scope: {finding.get('scope', {}).get('population')} ({finding.get('scope', {}).get('period')})",
              f"Data: {finding.get('data_source')}"]
    for e in finding.get("evidence", [])[:1]:
        points.append(f"Evidence ({e.get('source_file')}): {e.get('description')}")

    recs: list[dict[str, Any]] = []
    if task == "recommendations":
        recs.append({
            "action": "Confirm the measurement with the data or process owner and review the evidence records "
                      "before changing anything.",
            "rationale": "The value comes from the analytics module; owners can confirm the definition and the data.",
            "expected_benefit_hypothesis": "Avoids acting on a data or definition problem.",
            "risks": ["Review takes time while a real issue may continue."],
            "supporting_policy_chunk_ids": [],
        })
        if excerpts:
            top = excerpts[0]
            recs.append({
                "action": f"Compare current practice with '{top['section']}' in {top['source_file']} and decide "
                          f"whether practice or the documented expectation should change.",
                "rationale": "This is the closest policy passage found for the finding.",
                "expected_benefit_hypothesis": "Clarifies whether the gap is a practice problem or an unrealistic target.",
                "risks": ["The retrieved passage may not be the only relevant rule."],
                "supporting_policy_chunk_ids": [top["chunk_id"]],
            })
        domain = finding.get("domain")
        if finding.get("severity") in ("high", "medium"):
            extra = {
                "process": ("Look at waiting time versus working time for this stage and who owns the hand-off; "
                            "treat any cause as a hypothesis to test."),
                "hr": ("Discuss the department-level pattern with the department head and look for context; "
                       "avoid conclusions about individual people."),
                "business": "Treat this as context only; do not compare it directly with company performance.",
            }.get(domain, "Discuss the finding with the responsible owner.")
            recs.append({"action": extra, "rationale": "A medium or high severity finding deserves a follow-up.",
                         "expected_benefit_hypothesis": "Helps decide whether a change is justified.",
                         "risks": ["Findings are associations, not proven causes."],
                         "supporting_policy_chunk_ids": []})

    limitations = list(finding.get("limitations", []))
    limitations.append("Generated without an AI model (fallback mode): the wording is templated, not written by a model.")
    return {"summary": summary, "key_points": points, "recommendations": recs, "limitations": limitations}
