"""Prompt construction for the on-demand 'Propose Fix' step (see
design-notes/execution-plan-web-ui.md). Deliberately separate from
narration/prompt.py's explanation/overview prompt: that one runs on every
query; this one only runs when the user explicitly clicks Propose Fix,
since drafting a rewritten query or an index script is a slower, harder
ask for a small local model than a one-line explanation.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from querysmith.narration.models import PlanSummary
from querysmith.rules.models import Finding

__all__ = ["build_fix_prompt"]

SYSTEM_PREAMBLE = (
    "You are a database performance assistant. A deterministic rules engine has "
    "already analyzed a query execution plan and produced a prioritized list of "
    "findings, and a separate step has already explained them to the user in plain "
    "English. Your only job now is to propose concrete remediations for findings "
    "that don't already have one.\n\n"
    "Rules you must follow:\n"
    "- A finding may already include a non-null suggested_fix -- that came from the "
    "rules engine itself (e.g. a generated CREATE INDEX script) and is a verified "
    "fact. For that finding, set both rewritten_query and index_script to null: "
    "there is nothing for you to add.\n"
    "- For findings without one, propose either or both of:\n"
    "  - rewritten_query: a complete, valid T-SQL SELECT statement, referencing "
    "only the same tables/columns as the statement given below, that addresses the "
    "finding via a query-shape change (join order, join predicates, predicate "
    "placement, column selection). It must be a single SELECT statement -- no DDL, "
    "no comments, no markdown fences -- and must return the same rows/columns as "
    "the original, just structured to perform better.\n"
    "  - index_script: a complete, valid T-SQL CREATE INDEX statement (a single "
    "statement, no markdown fences) that would address the finding.\n"
    "- Only propose either field when you're confident it's correct and specific to "
    "this plan/statement. Set it to null rather than guessing.\n"
    "- Respond with a single JSON object and nothing else: no markdown fences, no "
    "commentary before or after the JSON.\n"
)

RESPONSE_SCHEMA_DESCRIPTION = (
    "Respond with exactly this JSON shape:\n"
    "{\n"
    '  "fixes": [\n'
    '    {"finding_index": <int, matches finding_index given below>, '
    '"rewritten_query": <"<complete rewritten SELECT statement>" or null>, '
    '"index_script": <"<complete CREATE INDEX statement>" or null>}\n'
    "  ]\n"
    "}\n"
    "Include exactly one fixes[] entry per finding_index given below, in any order."
)


def build_fix_prompt(plan_summary: PlanSummary, findings: list[Finding]) -> str:
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
