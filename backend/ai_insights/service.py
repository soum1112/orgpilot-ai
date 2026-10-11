"""Orchestration: finding -> policy excerpts -> language model -> validation -> (fallback) -> response."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from django.conf import settings

from . import adapters, fallback, llm, retrieval, validators

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the explanation assistant of OrgPilot AI, an organizational decision-support tool.
You receive ONE finding that Python already calculated and validated, plus policy excerpts with ids.
Rules:
1. Use only values that appear in the finding or the excerpts. Do not calculate new numbers, percentages or estimates, and do not write any number that is not in the input.
2. Never state a cause as fact. Describe possible explanations only as hypotheses to investigate.
3. Cite policy only with the chunk ids provided. Never invent a rule, document or citation.
4. If the evidence is not enough, say so in "limitations".
5. Recommendations are proposals for a human to review.
Reply with JSON only, exactly in this shape:
{"summary": "2-3 plain sentences", "key_points": ["..."], "recommendations": [{"action": "...", "rationale": "...", "expected_benefit_hypothesis": "...", "risks": ["..."], "supporting_policy_chunk_ids": ["..."]}], "limitations": ["..."]}"""

TASK_NOTE = {
    "analyze": "Task: explain the finding in plain words. Set \"recommendations\" to an empty list.",
    "recommendations": "Task: give 2 or 3 recommendations. Keep \"summary\" to one or two sentences.",
}


def _user_prompt(finding, excerpts, task, question, correction=None) -> str:
    parts = [TASK_NOTE[task], "FINDING:\n" + json.dumps(finding, default=str, indent=1),
             "POLICY EXCERPTS:\n" + (json.dumps(
                 [{"chunk_id": e["chunk_id"], "source": e["source_file"], "section": e["section"], "text": e["text"]}
                  for e in excerpts], indent=1) if excerpts else "none found")]
    if question:
        parts.append("USER QUESTION (answer only from the evidence above): " + question)
    if correction:
        parts.append("YOUR PREVIOUS ANSWER WAS REJECTED because it " + correction +
                     ". Answer again and follow the rules strictly.")
    return "\n\n".join(parts)


def run(task: str, finding_id: str, question: str | None = None, use_llm: bool = True) -> dict[str, Any]:
    """Returns the response envelope. Raises KeyError if the finding id is unknown."""
    finding, bundle = adapters.get_finding(finding_id)
    if finding is None:
        raise KeyError(finding_id)

    excerpts = retrieval.retrieve_for_finding(finding, question)
    llm_info: dict[str, Any] = {"status": "disabled", "model": settings.OLLAMA_MODEL, "detail": None}
    clean, notes, mode = None, [], "fallback"

    if use_llm:
        correction = None
        for attempt in (1, 2):                       # one retry with feedback, then give up
            try:
                raw = llm.chat_json(SYSTEM_PROMPT, _user_prompt(finding, excerpts, task, question, correction))
                clean, notes = validators.validate(raw, finding, excerpts, task, question)
                mode, llm_info = "llm", {"status": "ok", "model": settings.OLLAMA_MODEL, "detail": None}
                break
            except llm.LLMUnavailable as exc:
                llm_info = {"status": "unavailable", "model": settings.OLLAMA_MODEL, "detail": str(exc)}
                break                                # a retry will not help if the model is offline
            except llm.LLMBadOutput as exc:
                llm_info = {"status": "bad_output", "model": settings.OLLAMA_MODEL, "detail": str(exc)}
                correction = "was not valid JSON in the required shape"
            except validators.OutputRejected as exc:
                llm_info = {"status": "rejected", "model": settings.OLLAMA_MODEL, "detail": exc.reason}
                correction = exc.reason

    if clean is None:
        clean = fallback.build(finding, excerpts, task)

    warnings = list(bundle["warnings"]) + notes
    if mode == "fallback" and use_llm:
        warnings.append("The language model was not used for this answer (see llm.status); showing the template answer.")
    return {
        "status": "ok",
        "data": {
            "task": task,
            "mode": mode,
            "finding": finding,
            **clean,
            "policy_excerpts": excerpts,
            "human_review_required": True,
            "llm": llm_info,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "meta": {"source_files": bundle["source_files"] + sorted({e["source_file"] for e in excerpts}),
                 "warnings": warnings},
    }
