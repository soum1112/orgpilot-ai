"""Small Ollama client (standard library only). Never raises into the caller except the two errors below."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings


class LLMUnavailable(Exception):
    """Ollama is not running, the model is missing, or the call timed out."""


class LLMBadOutput(Exception):
    """The model answered, but not with usable JSON."""


def _request(path: str, payload: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
    url = settings.OLLAMA_URL.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                 method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout or settings.OLLAMA_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise LLMUnavailable(f"Ollama returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise LLMUnavailable(f"Cannot reach Ollama at {settings.OLLAMA_URL}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise LLMUnavailable("Ollama sent an unreadable response") from exc


def health() -> dict[str, Any]:
    """Quick check used by /api/ai/health/. Short timeout so the page never hangs."""
    info: dict[str, Any] = {"url": settings.OLLAMA_URL, "model": settings.OLLAMA_MODEL,
                            "reachable": False, "model_available": False, "detail": None}
    try:
        tags = _request("/api/tags", timeout=3)
    except LLMUnavailable as exc:
        info["detail"] = str(exc)
        return info
    names = [m.get("name", "") for m in tags.get("models", [])]
    info["reachable"] = True
    info["model_available"] = settings.OLLAMA_MODEL in names
    if not info["model_available"]:
        info["detail"] = f"Model not installed. Run: ollama pull {settings.OLLAMA_MODEL}"
    return info


def parse_json_object(text: str) -> dict[str, Any]:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise LLMBadOutput("The model did not return JSON")
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise LLMBadOutput("The model returned broken JSON") from exc
    if not isinstance(obj, dict):
        raise LLMBadOutput("The model returned JSON that is not an object")
    return obj


def chat_json(system: str, user: str) -> dict[str, Any]:
    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2},
    }
    reply = _request("/api/chat", payload)
    content = (reply.get("message") or {}).get("content", "")
    if not content.strip():
        raise LLMBadOutput("The model returned an empty answer")
    return parse_json_object(content)
