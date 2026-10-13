"""HTTP layer. Response envelope matches the team contract: {status, data{..., generated_at}, meta{source_files, warnings}}."""
from __future__ import annotations

from datetime import datetime, timezone

from rest_framework.response import Response
from rest_framework.views import APIView

from . import adapters, llm, retrieval, service

MAX_QUESTION = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _error(message: str, code: int) -> Response:
    return Response({"status": "error", "message": message}, status=code)


class Health(APIView):
    def get(self, request):
        index = retrieval.get_index().summary()
        bundle = adapters.collect_findings()
        modules_ok = all(v == "ok" for v in bundle["modules"].values())
        ollama = llm.health()
        return Response({
            "status": "ok" if modules_ok else "degraded",
            "data": {
                "ollama": ollama,
                "fallback_available": True,
                "policy_index": index,
                "modules": bundle["modules"],
                "finding_count": len(bundle["findings"]),
                "generated_at": _now(),
            },
            "meta": {"source_files": [], "warnings": bundle["warnings"] + index["warnings"]},
        })


class Findings(APIView):
    """Every module's findings in the shared format. Optional filters: ?domain=hr|process|business&severity=high"""

    def get(self, request):
        bundle = adapters.collect_findings()
        items = bundle["findings"]
        domain, severity = request.query_params.get("domain"), request.query_params.get("severity")
        if domain:
            items = [f for f in items if f["domain"] == domain]
        if severity:
            items = [f for f in items if f["severity"] == severity]
        return Response({
            "status": "ok",
            "data": {"total": len(items), "items": items, "modules": bundle["modules"], "generated_at": _now()},
            "meta": {"source_files": bundle["source_files"], "warnings": bundle["warnings"]},
        })


class _AiBase(APIView):
    task = ""

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        finding_id = body.get("finding_id")
        if not isinstance(finding_id, str) or not finding_id.strip():
            return _error("Send JSON like {\"finding_id\": \"PROC-001\"}. Get ids from GET /api/ai/findings/.", 400)
        question = body.get("question")
        if question is not None and (not isinstance(question, str) or len(question) > MAX_QUESTION):
            return _error(f"'question' must be text of at most {MAX_QUESTION} characters.", 400)
        use_llm = body.get("use_llm", True)
        if not isinstance(use_llm, bool):
            return _error("'use_llm' must be true or false.", 400)
        try:
            return Response(service.run(self.task, finding_id.strip(), question, use_llm))
        except KeyError:
            return _error(f"Unknown finding_id '{finding_id}'.", 404)


class Analyze(_AiBase):
    task = "analyze"


class Recommendations(_AiBase):
    task = "recommendations"
