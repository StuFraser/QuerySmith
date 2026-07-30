"""Thin stdlib-only HTTP boundary to a local Ollama server's /api/generate
endpoint, using JSON mode for structured output (see
design-notes/execution-plan-agent-scope.md). No new dependency -- urllib.request
only. Single swappable function so callers/tests can inject a fake.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

__all__ = ["generate_json", "OllamaClientError"]

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_TIMEOUT_S = 30.0


class OllamaClientError(Exception):
    """Server unreachable, timed out, non-2xx HTTP status, or a response that
    isn't valid JSON despite requesting JSON mode. Callers catch this single
    type and degrade gracefully rather than propagating it."""


def generate_json(
    prompt: str,
    model: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict:
    payload = json.dumps({"model": model, "prompt": prompt, "format": "json", "stream": False}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        raise OllamaClientError(f"Ollama returned HTTP {exc.code}") from exc
    except OSError as exc:  # covers URLError, timeouts, connection refused, DNS, etc.
        raise OllamaClientError(f"Ollama request failed: {exc}") from exc

    try:
        envelope = json.loads(body)
    except json.JSONDecodeError as exc:
        raise OllamaClientError(f"Ollama response envelope was not valid JSON: {exc}") from exc

    inner_text = envelope.get("response") if isinstance(envelope, dict) else None
    if not isinstance(inner_text, str):
        raise OllamaClientError("Ollama response envelope missing string 'response' field")

    try:
        return json.loads(inner_text)
    except json.JSONDecodeError as exc:
        raise OllamaClientError(f"Model response was not valid JSON despite format=json: {exc}") from exc
