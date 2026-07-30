"""Tier 0 deterministic rules engine (see design-notes/execution-plan-agent-scope.md).

Pure function over the IR -- no model calls, no I/O, no live DB. `evaluate` is
the only public entry point; Tier 1/2 narrate its output and never re-derive
or reprioritize it (the scope doc's phrase is "explain + present in given
order" -- ordering is this module's responsibility, not the model's).
"""

from __future__ import annotations

from querysmith.ir.models import (
    AccessType,
    IRPlan,
    Operator,
    OperatorType,
    Severity,
    WarningType,
)
from querysmith.rules.models import Finding

__all__ = ["evaluate"]

# Row-count thresholds for flagging a scan/full-scan as worth surfacing.
# Arbitrary but documented -- tune here, not scattered through the rule body.
LARGE_SCAN_WARNING_ROWS = 10_000
LARGE_SCAN_CRITICAL_ROWS = 100_000

# row_estimate_ratio outside [SKEW_RATIO_LOW, SKEW_RATIO_HIGH] is flagged.
SKEW_RATIO_HIGH = 10.0
SKEW_RATIO_LOW = 0.1

MISSING_INDEX_IMPACT_CRITICAL = 80.0
MISSING_INDEX_IMPACT_WARNING = 50.0

_SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}

# Severity assigned when Tier 0 promotes an adapter-sourced Warning into a
# Finding. Adapters never set severity themselves (see IR doc) -- this map is
# the one place that judgment call is made, deterministically rather than
# per-plan.
_PROMOTED_WARNING_SEVERITY = {
    WarningType.TEMPDB_SPILL: Severity.CRITICAL,
    WarningType.NO_JOIN_PREDICATE: Severity.CRITICAL,
    WarningType.IMPLICIT_CONVERSION: Severity.WARNING,
    WarningType.COLUMN_WITH_NO_STATS: Severity.WARNING,
    WarningType.MEMORY_GRANT_EXCESSIVE: Severity.WARNING,
    WarningType.CARDINALITY_SKEW: Severity.WARNING,
    WarningType.OTHER: Severity.INFO,
}

_PROMOTED_WARNING_SUMMARY = {
    WarningType.TEMPDB_SPILL: "Operator spilled to tempdb",
    WarningType.NO_JOIN_PREDICATE: "Join has no predicate (possible cartesian product)",
    WarningType.IMPLICIT_CONVERSION: "Implicit type conversion may block index usage",
    WarningType.COLUMN_WITH_NO_STATS: "Column has no statistics",
    WarningType.MEMORY_GRANT_EXCESSIVE: "Memory grant may be excessive",
    WarningType.CARDINALITY_SKEW: "Engine-reported cardinality estimate skew",
    WarningType.OTHER: "Engine-reported plan warning",
}


def evaluate(plan: IRPlan) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(_promote_adapter_warnings(plan))
    findings.extend(_check_large_scans(plan.root_operator))
    findings.extend(_check_cardinality_skew(plan.root_operator))
    findings.extend(_check_bookmark_lookups(plan.root_operator))
    findings.extend(_check_missing_indexes(plan))
    findings.extend(_check_parallelism(plan.root_operator))
    # Stable sort: within a severity, rule execution order above is preserved.
    findings.sort(key=lambda f: _SEVERITY_ORDER[f.severity])
    return findings


def _walk(op: Operator):
    yield op
    for child in op.children:
        yield from _walk(child)


def _promote_adapter_warnings(plan: IRPlan) -> list[Finding]:
    findings = []
    for warning in plan.warnings:
        findings.append(
            Finding(
                rule_id=f"adapter_warning.{warning.type.value}",
                severity=_PROMOTED_WARNING_SEVERITY.get(warning.type, Severity.INFO),
                operator_id=warning.operator_id,
                summary=_PROMOTED_WARNING_SUMMARY.get(warning.type, "Engine-reported plan warning"),
                detail=warning.detail,
            )
        )
    return findings


def _check_large_scans(root: Operator) -> list[Finding]:
    findings = []
    for op in _walk(root):
        if op.access_type not in (AccessType.SCAN, AccessType.FULL_SCAN):
            continue
        rows = op.actual_rows if op.actual_rows is not None else op.estimated_rows
        if rows is None:
            continue
        if rows >= LARGE_SCAN_CRITICAL_ROWS:
            severity = Severity.CRITICAL
        elif rows >= LARGE_SCAN_WARNING_ROWS:
            severity = Severity.WARNING
        else:
            continue
        table = op.object_ref.table if op.object_ref and op.object_ref.table else "unknown table"
        findings.append(
            Finding(
                rule_id="large_table_scan",
                severity=severity,
                operator_id=op.id,
                summary=f"{op.operator_type.value} reads ~{int(rows):,} rows from {table}",
                detail=f"physical_op={op.physical_op_raw}, access_type={op.access_type.value}, rows={rows}",
            )
        )
    return findings


def _check_cardinality_skew(root: Operator) -> list[Finding]:
    findings = []
    for op in _walk(root):
        ratio = op.row_estimate_ratio
        if ratio is None:
            continue
        if ratio >= SKEW_RATIO_HIGH:
            direction = "under-estimated"
        elif ratio <= SKEW_RATIO_LOW:
            direction = "over-estimated"
        else:
            continue
        findings.append(
            Finding(
                rule_id="cardinality_skew",
                severity=Severity.WARNING,
                operator_id=op.id,
                summary=f"Optimizer {direction} row count at {op.operator_type.value} (ratio {ratio:.2g})",
                detail=f"estimated_rows={op.estimated_rows}, actual_rows={op.actual_rows}",
            )
        )
    return findings


def _check_bookmark_lookups(root: Operator) -> list[Finding]:
    findings = []
    for op in _walk(root):
        if op.operator_type != OperatorType.BOOKMARK_LOOKUP:
            continue
        table = op.object_ref.table if op.object_ref and op.object_ref.table else "unknown table"
        findings.append(
            Finding(
                rule_id="non_covering_key_lookup",
                severity=Severity.WARNING,
                operator_id=op.id,
                summary=f"Key lookup against {table} -- consider a covering index",
                detail=f"physical_op={op.physical_op_raw}, predicates={op.predicates}",
            )
        )
    return findings


def _check_missing_indexes(plan: IRPlan) -> list[Finding]:
    findings = []
    for mi in plan.missing_indexes:
        impact = mi.estimated_impact
        if impact is not None and impact >= MISSING_INDEX_IMPACT_CRITICAL:
            severity = Severity.CRITICAL
        elif impact is not None and impact >= MISSING_INDEX_IMPACT_WARNING:
            severity = Severity.WARNING
        else:
            severity = Severity.INFO
        impact_text = f"{impact}" if impact is not None else "unknown"
        findings.append(
            Finding(
                rule_id="missing_index_available",
                severity=severity,
                operator_id=None,
                summary=f"Engine suggests an index on {mi.table} (impact {impact_text})",
                detail=(
                    f"equality={mi.columns_equality}, inequality={mi.columns_inequality}, "
                    f"include={mi.columns_include}"
                ),
            )
        )
    return findings


def _check_parallelism(root: Operator) -> list[Finding]:
    if not root.parallel:
        return []
    return [
        Finding(
            rule_id="parallelism_used",
            severity=Severity.INFO,
            operator_id=root.id,
            summary="Plan executed with parallelism",
            detail="Root operator ran in parallel; not inherently bad, but worth noting for small/OLTP workloads.",
        )
    ]
