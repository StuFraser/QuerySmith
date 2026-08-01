"""Tier 1 local SLM narration (see design-notes/execution-plan-agent-scope.md).

`get_narration` is the only public entry point. It never re-derives or
reprioritizes Tier 0's findings -- it iterates `findings` (the authoritative
list, in Tier 0's order) and asks the model only to explain each one. The
model's own response is never trusted as the source of order, shape, or
membership: unmatched, reordered, duplicated, or hallucinated entries are all
tolerated without corrupting the output. Correlation key is `finding_index`
(list position), not `rule_id` -- rule_id is not unique per findings list
(e.g. multiple large_table_scan findings can co-exist).

If the model is unreachable or returns nothing usable, this degrades in place
rather than raising: Tier 0's own already-human-readable `summary`/`detail`
become the explanation, and the whole tool remains usable with no local model
running at all.
"""

from __future__ import annotations

from collections import Counter
from typing import Callable, Optional

from querysmith.ir.models import Severity
from querysmith.narration.models import FindingNarration, Narration, PlanSummary
from querysmith.narration.ollama_client import OllamaClientError, generate_json
from querysmith.narration.prompt import build_prompt
from querysmith.rules.models import Finding

__all__ = ["get_narration", "DEFAULT_MODEL"]

GenerateFn = Callable[[str, str], dict]

# Verified against real hardware (7.6GB RAM, CPU-only): llama3.1:8b OOM'd and
# errored out after several minutes; llama3.2:3b ran end-to-end (~2.5 tok/s,
# slow but stable). Still worth benchmarking Qwen2.5 / Phi-4 variants against
# your own hardware -- always overridable via `model=`.
DEFAULT_MODEL = "llama3.2:3b"

_SEVERITY_ORDER = (Severity.CRITICAL, Severity.WARNING, Severity.INFO)


def get_narration(
    findings: list[Finding],
    plan_summary: PlanSummary,
    *,
    model: str = DEFAULT_MODEL,
    client: Optional[GenerateFn] = None,
) -> Narration:
    # `client` defaults to None (rather than binding `generate_json` directly
    # as the default value) so it's resolved here, at call time -- this is
    # what makes the real network call swappable via a module-level patch,
    # not just via the `client=` kwarg.
    if client is None:
        client = generate_json

    prompt = build_prompt(plan_summary, findings)

    raw: Optional[dict] = None
    degraded_reason: Optional[str] = None
    try:
        response = client(prompt, model)
        if isinstance(response, dict):
            raw = response
        else:
            degraded_reason = "invalid_response_shape"
    except OllamaClientError as exc:
        degraded_reason = f"client_error: {exc}"

    explanations = _extract_explanations(raw, len(findings)) if raw is not None else {}
    model_fixes = _extract_suggested_fixes(raw, len(findings)) if raw is not None else {}

    finding_narrations = []
    for idx, finding in enumerate(findings):
        model_explanation = explanations.get(idx)
        if model_explanation:
            explanation, source = model_explanation, "model"
        else:
            explanation, source = _fallback_explanation(finding), "fallback"
        # Tier 0's own fix (if any) is a verified fact and always wins; the
        # model is never the source of a fix for a finding Tier 0 already
        # solved, and there's no fabricated fallback when the model gives
        # nothing usable -- absence is shown as no fix, not an invented one.
        suggested_fix = None if finding.suggested_fix else model_fixes.get(idx)
        finding_narrations.append(
            FindingNarration(
                rule_id=finding.rule_id,
                severity=finding.severity,
                operator_id=finding.operator_id,
                summary=finding.summary,
                detail=finding.detail,
                explanation=explanation,
                explanation_source=source,
                suggested_fix=suggested_fix,
            )
        )

    overview_raw = raw.get("overview") if isinstance(raw, dict) else None
    if isinstance(overview_raw, str) and overview_raw.strip():
        overview, overview_source = overview_raw.strip(), "model"
    else:
        overview, overview_source = _fallback_overview(plan_summary, findings), "fallback"

    model_contributed = overview_source == "model" or any(fn.explanation_source == "model" for fn in finding_narrations)
    degraded = not model_contributed
    if not degraded:
        degraded_reason = None
    elif degraded_reason is None:
        degraded_reason = "invalid_response_shape"

    return Narration(
        overview=overview,
        overview_source=overview_source,
        findings=finding_narrations,
        degraded=degraded,
        degraded_reason=degraded_reason,
        model_name=model,
    )


def _extract_explanations(raw: Optional[dict], num_findings: int) -> dict[int, str]:
    result: dict[int, str] = {}
    items = raw.get("findings") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return result
    for item in items:
        if not isinstance(item, dict):
            continue
        idx = item.get("finding_index")
        explanation = item.get("explanation")
        if not isinstance(idx, int) or not isinstance(explanation, str) or not explanation.strip():
            continue
        if not (0 <= idx < num_findings):
            continue  # hallucinated out-of-range index -- ignore
        if idx in result:
            continue  # duplicate -- first occurrence wins
        result[idx] = explanation.strip()
    return result


def _extract_suggested_fixes(raw: Optional[dict], num_findings: int) -> dict[int, str]:
    result: dict[int, str] = {}
    items = raw.get("findings") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return result
    for item in items:
        if not isinstance(item, dict):
            continue
        idx = item.get("finding_index")
        fix = item.get("suggested_fix")
        if not isinstance(idx, int) or not isinstance(fix, str) or not fix.strip():
            continue  # null/missing/non-string -- model chose not to propose one
        if not (0 <= idx < num_findings):
            continue  # hallucinated out-of-range index -- ignore
        if idx in result:
            continue  # duplicate -- first occurrence wins
        result[idx] = fix.strip()
    return result


def _fallback_explanation(finding: Finding) -> str:
    return f"{finding.summary}. {finding.detail}".strip()


def _fallback_overview(plan_summary: PlanSummary, findings: list[Finding]) -> str:
    counts = Counter(f.severity for f in findings)
    parts = [f"{counts[s]} {s.value}" for s in _SEVERITY_ORDER if counts.get(s)]
    counts_text = ", ".join(parts) if parts else "no findings"
    subject = plan_summary.object_name or f"this {plan_summary.statement_type.lower()} statement"
    return (
        f"Automated narration was unavailable for this plan. Showing the rules "
        f"engine's own findings for {subject}: {counts_text}."
    )
