"""Real end-to-end smoke test against a live Ollama server. Skipped unless
QUERYSMITH_OLLAMA_INTEGRATION=1 is set AND a server actually answers -- a
plain `pytest -v` run requires zero network access.
"""

import os
import urllib.error
import urllib.request

import pytest

from querysmith.narration import DEFAULT_MODEL, get_narration, summarize_plan
from querysmith.narration.ollama_client import DEFAULT_BASE_URL


def _ollama_reachable() -> bool:
    try:
        urllib.request.urlopen(f"{DEFAULT_BASE_URL}/api/tags", timeout=1.0)
        return True
    except (urllib.error.URLError, OSError):
        return False


_ENABLED = os.environ.get("QUERYSMITH_OLLAMA_INTEGRATION") == "1"


@pytest.mark.skipif(not _ENABLED, reason="QUERYSMITH_OLLAMA_INTEGRATION not set")
@pytest.mark.skipif(_ENABLED and not _ollama_reachable(), reason="No Ollama server reachable")
def test_get_narration_against_live_ollama(op_factory, plan_factory, finding_factory):
    plan = plan_factory(op_factory())
    summary = summarize_plan(plan)
    findings = [finding_factory()]

    narration = get_narration(findings, summary, model=DEFAULT_MODEL)
    assert narration.overview
    assert len(narration.findings) == 1
