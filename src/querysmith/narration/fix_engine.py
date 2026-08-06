"""On-demand ('Propose Fix' button) Tier 1 remediation drafting -- kept
separate from narration/engine.py's get_narration because it's an explicit,
user-triggered second step (see design-notes/execution-plan-web-ui.md), not
part of every query run. `propose_fixes` is the only public entry point.

Same correlation/trust posture as get_narration: `finding_index` (list
position) ties a model response back to Tier 0's authoritative findings
list, and unmatched/out-of-range/duplicate entries are tolerated without
corrupting the output. Unlike get_narration, there is no fallback synthesis
here -- a finding either gets a model-proposed fix or it doesn't, and
nothing the model returns is trusted as safe SQL until it's re-validated
(rewritten_query via query_safety.validate_select_only, index_script via
query_safety.validate_create_index_only).
"""

from __future__ import annotations

from typing import Callable, Optional

from querysmith.db.query_safety import QueryValidationError, validate_create_index_only, validate_select_only
from querysmith.narration.engine import DEFAULT_MODEL
from querysmith.narration.fix_prompt import build_fix_prompt
from querysmith.narration.models import FindingFix, FixProposal, PlanSummary
from querysmith.narration.ollama_client import OllamaClientError, generate_json
from querysmith.rules.models import Finding

__all__ = ["propose_fixes"]

GenerateFn = Callable[[str, str], dict]


def propose_fixes(
    findings: list[Finding],
    plan_summary: PlanSummary,
    *,
    model: str = DEFAULT_MODEL,
    client: Optional[GenerateFn] = None,
) -> FixProposal:
    if client is None:
        client = generate_json

    prompt = build_fix_prompt(plan_summary, findings)

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

    rewrites = _extract_field(raw, len(findings), "rewritten_query", validate_select_only)
    index_scripts = _extract_field(raw, len(findings), "index_script", validate_create_index_only)

    fixes = []
    for idx, finding in enumerate(findings):
        # Tier 0's own fix always wins -- never let the model add anything
        # for a finding it already solved, regardless of what it returned.
        if finding.suggested_fix:
            continue
        rewritten_query = rewrites.get(idx)
        index_script = index_scripts.get(idx)
        if rewritten_query or index_script:
            fixes.append(
                FindingFix(finding_index=idx, rewritten_query=rewritten_query, index_script=index_script)
            )

    # raw is None exactly when the call itself failed (client error or a
    # non-dict response) -- a successful call that simply had nothing to
    # propose is not a degraded run, just an empty one.
    degraded = raw is None
    return FixProposal(
        fixes=fixes,
        degraded=degraded,
        degraded_reason=degraded_reason if degraded else None,
        model_name=model,
    )


def _extract_field(
    raw: Optional[dict], num_findings: int, key: str, validator: Callable[[str], str]
) -> dict[int, str]:
    result: dict[int, str] = {}
    items = raw.get("fixes") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return result
    for item in items:
        if not isinstance(item, dict):
            continue
        idx = item.get("finding_index")
        value = item.get(key)
        if not isinstance(idx, int) or not isinstance(value, str) or not value.strip():
            continue  # null/missing/non-string -- model chose not to propose one
        if not (0 <= idx < num_findings):
            continue  # hallucinated out-of-range index -- ignore
        if idx in result:
            continue  # duplicate -- first occurrence wins
        try:
            # Fails closed: anything that isn't exactly the expected single
            # statement shape (prose, wrong statement type, stacked
            # statements, a parse error) is dropped rather than surfaced.
            validator(value.strip())
        except QueryValidationError:
            continue
        result[idx] = value.strip()
    return result
