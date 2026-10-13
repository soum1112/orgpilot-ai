"""Guardrails for model output.

The model may only explain and propose. It is rejected if it:
  * is not the expected JSON shape,
  * writes a number that is not in the finding or the retrieved policy text (no invented figures),
  * states a cause as fact ("caused by", "root cause is" ...).
Policy citations that were not retrieved are dropped. `human_review_required` is set by the server, not the model.
"""
from __future__ import annotations

import json
import re
from typing import Any

_NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_CAUSAL = re.compile(
    r"\b(caused by|is caused|are caused|because of|as a result of|proves?|proven|root cause (is|was)|"
    r"is responsible for|are responsible for|is due to|are due to)\b", re.I)


class OutputRejected(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def extract_numbers(text: str) -> list[float]:
    out = []
    for m in _NUMBER.findall(text or ""):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def allowed_numbers(finding: dict[str, Any], excerpts: list[dict[str, Any]], question: str | None) -> list[float]:
    blob = json.dumps(finding, default=str) + " " + " ".join(e.get("text", "") + " " + e.get("section", "") for e in excerpts)
    return extract_numbers(blob + " " + (question or ""))


def _supported(value: float, allowed: list[float]) -> bool:
    return any(abs(value - a) <= max(0.06, 0.01 * abs(a)) for a in allowed)


def _str(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def _str_list(v: Any, limit: int = 6) -> list[str]:
    return [s for s in (_str(x) for x in v[:limit]) if s] if isinstance(v, list) else []


def validate(obj: dict[str, Any], finding: dict[str, Any], excerpts: list[dict[str, Any]], task: str,
             question: str | None = None) -> tuple[dict[str, Any], list[str]]:
    """Return (clean_output, notes). Raise OutputRejected when the answer must not be shown."""
    notes: list[str] = []
    summary = _str(obj.get("summary"))
    if not summary:
        raise OutputRejected("missing 'summary'")
    key_points = _str_list(obj.get("key_points"))
    limitations = _str_list(obj.get("limitations"))
    valid_ids = {e["chunk_id"] for e in excerpts}

    recs = []
    raw_recs = obj.get("recommendations")
    if raw_recs is not None and not isinstance(raw_recs, list):
        raise OutputRejected("'recommendations' is not a list")
    for r in (raw_recs or [])[:4]:
        if not isinstance(r, dict) or not _str(r.get("action")):
            raise OutputRejected("a recommendation has no 'action'")
        cited = [c for c in (r.get("supporting_policy_chunk_ids") or []) if isinstance(c, str)]
        dropped = [c for c in cited if c not in valid_ids]
        if dropped:
            notes.append(f"Removed citation(s) that were not retrieved: {', '.join(dropped)}")
        recs.append({
            "action": _str(r.get("action")),
            "rationale": _str(r.get("rationale")),
            "expected_benefit_hypothesis": _str(r.get("expected_benefit_hypothesis")),
            "risks": _str_list(r.get("risks"), 4),
            "supporting_policy_chunk_ids": [c for c in cited if c in valid_ids],
        })
    if task == "recommendations" and not recs:
        raise OutputRejected("no recommendations were returned")

    texts = [summary, *key_points, *limitations]
    for r in recs:
        texts += [r["action"], r["rationale"], r["expected_benefit_hypothesis"], *r["risks"]]
    allowed = allowed_numbers(finding, excerpts, question)
    bad = sorted({n for t in texts for n in extract_numbers(t) if not _supported(n, allowed)})
    if bad:
        raise OutputRejected(f"contains numbers that are not in the evidence: {bad[:5]}")
    for t in texts:
        m = _CAUSAL.search(t)
        if m:
            raise OutputRejected(f"states a cause as fact ('{m.group(0)}')")

    return ({"summary": summary, "key_points": key_points, "recommendations": recs,
             "limitations": limitations}, notes)
