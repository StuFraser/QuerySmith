"""Prompt construction for Tier 1 narration. Pure function -- fully
unit-testable with no model call (see design-notes/execution-plan-agent-scope.md).
"""

from __future__ import annotations

import json
from dataclasses import asdict

from querysmith.narration.models import PlanSummary
from querysmith.rules.models import Finding

__all__ = ["build_prompt"]

SYSTEM_PREAMBLE = (
    "You are a database performance assistant. A deterministic rules engine has "
    "already analyzed a query execution plan and produced a prioritized list of "
    "findings. Your job is to explain these findings in plain English for a "
    "developer audience, write a short overview of the plan as a whole, and -- "
    "where you can do so with confidence -- suggest a fix.\n\n"
    "Rules you must follow:\n"
    "- Do not reorder, omit, merge, or add findings. Explain each one exactly as given.\n"
    "- Do not change or second-guess any finding's severity or substance -- you are "
    "narrating, not re-analyzing.\n"
    "- A finding may already include a non-null suggested_fix -- that came from the "
    "rules engine itself (e.g. a generated CREATE INDEX script) and is a verified fact, "
    "not a suggestion. If you see one, set your own suggested_fix to null for that "
    "finding rather than repeating or contradicting it.\n"
    "- For findings without one, only propose a suggested_fix when the plan/statement "
    "gives you a concrete, specific basis for it (e.g. the statement text shows "
    "SELECT * with no WHERE clause). Set it to null rather than guessing a generic fix.\n"
    "- Respond with a single JSON object and nothing else: no markdown fences, no "
    "commentary before or after the JSON.\n"
)

RESPONSE_SCHEMA_DESCRIPTION = (
    "Respond with exactly this JSON shape:\n"
    "{\n"
    '  "overview": "<2-4 sentence plain-English summary of the plan as a whole>",\n'
    '  "findings": [\n'
    '    {"finding_index": <int, matches finding_index given below>, '
    '"explanation": "<1-3 sentence plain-English explanation>", '
    '"suggested_fix": <"<1-2 sentence specific remediation suggestion>" or null>}\n'
    "  ]\n"
    "}\n"
    "Include exactly one findings[] entry per finding_index given below, in any order."
)


def build_prompt(plan_summary: PlanSummary, findings: list[Finding]) -> str:
    summary_json = json.dumps(asdict(plan_summary), indent=2)
    findings_json = json.dumps(
        [
            {
                "finding_index": i,
                "rule_id": f.rule_id,
                "severity": f.severity.value,
                "operator_id": f.operator_id,
                "summary": f.summary,
                "detail": f.detail,
                "suggested_fix": f.suggested_fix,
            }
            for i, f in enumerate(findings)
        ],
        indent=2,
    )
    return (
        f"{SYSTEM_PREAMBLE}\n"
        f"## Plan summary\n{summary_json}\n\n"
        f"## Findings (already prioritized by the rules engine -- do not reorder)\n{findings_json}\n\n"
        f"## Output format\n{RESPONSE_SCHEMA_DESCRIPTION}\n"
    )
