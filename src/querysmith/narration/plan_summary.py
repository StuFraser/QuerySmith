"""IRPlan -> PlanSummary: condensed, prompt-friendly plan context (see
design-notes/execution-plan-agent-scope.md). The full recursive operator tree
is too verbose for a prompt -- this keeps only plan/statement identity, top-
level numbers, and a short, deterministically ranked list of notable
operators. Pure function, no I/O.
"""

from __future__ import annotations

from querysmith.ir.models import IRPlan, Operator
from querysmith.narration.models import OperatorHighlight, PlanSummary

__all__ = ["summarize_plan"]

# Caps that bound prompt size for large stored procs. Not doc-specified --
# defensive defaults, both overridable per call.
DEFAULT_MAX_NOTABLE_OPERATORS = 8
DEFAULT_MAX_STATEMENT_TEXT_CHARS = 4000


def summarize_plan(
    plan: IRPlan,
    *,
    max_notable_operators: int = DEFAULT_MAX_NOTABLE_OPERATORS,
    max_statement_text_chars: int = DEFAULT_MAX_STATEMENT_TEXT_CHARS,
) -> PlanSummary:
    operators = list(_walk(plan.root_operator))
    notable = _select_notable_operators(operators, max_notable_operators)

    statement_text = plan.statement.text
    if len(statement_text) > max_statement_text_chars:
        statement_text = statement_text[:max_statement_text_chars] + " ...[truncated]"

    return PlanSummary(
        engine=plan.meta.engine.value,
        engine_version=plan.meta.engine_version,
        database_name=plan.meta.database_name,
        object_type=plan.meta.object_type.value,
        object_name=plan.meta.object_name,
        plan_source=plan.meta.plan_source.value,
        statement_type=plan.statement.statement_type.value,
        statement_text=statement_text,
        total_estimated_cost=plan.statement.total_estimated_cost,
        total_actual_duration_ms=plan.statement.total_actual_duration_ms,
        total_actual_rows=plan.statement.total_actual_rows,
        operator_count=len(operators),
        notable_operators=[_to_highlight(op) for op in notable],
    )


def _walk(op: Operator):
    yield op
    for child in op.children:
        yield from _walk(child)


def _select_notable_operators(operators: list[Operator], limit: int) -> list[Operator]:
    # Ranked by cost share (nulls last), tied-broken by actual duration, then
    # id for full determinism. Deliberately plain cost/duration ranking, not a
    # special-cased "interesting operator" detector -- spills/lookups/skew are
    # already surfaced as their own Tier 0 findings, so this is a different,
    # complementary lens ("where does cost concentrate").
    def sort_key(op: Operator):
        cost = op.estimated_cost_pct_of_total if op.estimated_cost_pct_of_total is not None else -1.0
        duration = op.actual_duration_ms if op.actual_duration_ms is not None else -1.0
        return (-cost, -duration, op.id)

    return sorted(operators, key=sort_key)[:limit]


def _to_highlight(op: Operator) -> OperatorHighlight:
    object_ref = None
    if op.object_ref:
        parts = [p for p in (op.object_ref.schema, op.object_ref.table) if p]
        object_ref = ".".join(parts) if parts else None
    return OperatorHighlight(
        id=op.id,
        operator_type=op.operator_type.value,
        physical_op_raw=op.physical_op_raw,
        object_ref=object_ref,
        access_type=op.access_type.value if op.access_type else None,
        estimated_rows=op.estimated_rows,
        actual_rows=op.actual_rows,
        row_estimate_ratio=op.row_estimate_ratio,
        estimated_cost_pct_of_total=op.estimated_cost_pct_of_total,
        actual_duration_ms=op.actual_duration_ms,
        tempdb_spill=op.tempdb_spill,
        parallel=op.parallel,
    )
