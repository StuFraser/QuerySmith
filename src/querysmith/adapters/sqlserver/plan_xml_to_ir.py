"""SQL Server showplan XML -> dialect-agnostic IR (see design-notes/execution-plan-ir-schema.md).

Public surface is `parse_plan_xml` only -- IR consumers (Tier 0 rules engine,
Tier 1/2 model prompts) must never see raw showplan XML or lxml elements.
"""

from __future__ import annotations

import itertools
import logging
from datetime import datetime
from typing import Optional

from lxml import etree

from querysmith.adapters.sqlserver.operator_map import (
    HASH_JOIN_LOGICAL_OPS,
    HASH_MATCH_LOGICAL_OP_MAP,
    LOOKUP_CAPABLE_PHYSICAL_OPS,
    PHYSICAL_OP_MAP,
    WARNING_TAG_MAP,
)
from querysmith.ir.models import (
    AccessType,
    Engine,
    IRPlan,
    JoinType,
    MissingIndex,
    ObjectRef,
    ObjectType,
    Operator,
    OperatorType,
    PlanMeta,
    PlanSource,
    Statement,
    StatementType,
    Warning,
    WarningType,
)

__all__ = ["parse_plan_xml"]

SHOWPLAN_NS = "http://schemas.microsoft.com/sqlserver/2004/07/showplan"
NSMAP = {"sp": SHOWPLAN_NS}

logger = logging.getLogger(__name__)

_NON_WRAPPER_TAGS = {"OutputList", "RunTimeInformation", "Warnings", "RelOp"}


def parse_plan_xml(
    xml: str | bytes,
    *,
    plan_source: PlanSource = PlanSource.ESTIMATED,
    engine_version: Optional[str] = None,
    object_type: ObjectType = ObjectType.ADHOC_QUERY,
    object_name: Optional[str] = None,
    database_name: Optional[str] = None,
    captured_at: Optional[datetime] = None,
    redact: bool = False,
) -> IRPlan:
    data = xml.encode("utf-8") if isinstance(xml, str) else xml
    root = etree.fromstring(data)

    stmt_elem = root.find(".//sp:StmtSimple", NSMAP)
    if stmt_elem is None:
        raise ValueError("No StmtSimple element found in plan XML")
    query_plan_elem = stmt_elem.find("sp:QueryPlan", NSMAP)
    if query_plan_elem is None:
        raise ValueError("No QueryPlan element found in plan XML")
    rel_op_elem = query_plan_elem.find("sp:RelOp", NSMAP)
    if rel_op_elem is None:
        raise ValueError("No root RelOp element found in plan XML")

    total_cost = _get_float(stmt_elem, "StatementSubTreeCost")
    counter = itertools.count(1)
    warnings: list[Warning] = []
    root_operator = _build_operator_tree(rel_op_elem, total_cost, plan_source, counter, warnings)

    # SQL Server exposes memory grants once per plan, not per operator --
    # attributing it to any node other than root would fabricate a per-node
    # breakdown the engine doesn't provide.
    memory_grant_elem = query_plan_elem.find("sp:MemoryGrantInfo", NSMAP)
    if memory_grant_elem is not None:
        granted = memory_grant_elem.get("GrantedMemory")
        if granted is not None:
            root_operator.memory_grant_kb = int(float(granted))

    missing_indexes = _extract_missing_indexes(query_plan_elem)

    db_name = database_name
    if db_name is None:
        obj = query_plan_elem.find(".//sp:Object[@Database]", NSMAP)
        if obj is not None:
            db_name = _strip_brackets(obj.get("Database"))

    meta = PlanMeta(
        engine=Engine.SQLSERVER,
        engine_version=engine_version,
        plan_source=plan_source,
        captured_at=captured_at,
        object_type=object_type,
        object_name=object_name,
        database_name=db_name,
    )

    statement_text = stmt_elem.get("StatementText", "")
    if redact:
        statement_text = _redact_literals(statement_text)

    is_actual = plan_source == PlanSource.ACTUAL
    statement = Statement(
        text=statement_text,
        statement_type=_map_statement_type(stmt_elem.get("StatementType", "")),
        total_estimated_cost=total_cost,
        total_actual_duration_ms=root_operator.actual_duration_ms if is_actual else None,
        total_actual_rows=(
            int(root_operator.actual_rows) if is_actual and root_operator.actual_rows is not None else None
        ),
    )

    return IRPlan(
        meta=meta,
        statement=statement,
        root_operator=root_operator,
        warnings=warnings,
        missing_indexes=missing_indexes,
    )


def _build_operator_tree(rel_op_elem, total_cost, plan_source, counter, warnings_out) -> Operator:
    node_id = rel_op_elem.get("NodeId") or str(next(counter))
    physical_op = rel_op_elem.get("PhysicalOp", "")
    logical_op = rel_op_elem.get("LogicalOp", "")

    wrapper = _find_detail_wrapper(rel_op_elem)
    is_lookup = wrapper is not None and wrapper.get("Lookup") == "1"

    estimated_rows = _get_float(rel_op_elem, "EstimateRows")
    estimated_cost = _get_float(rel_op_elem, "EstimatedTotalSubtreeCost")

    runtime_info = rel_op_elem.find("sp:RunTimeInformation", NSMAP) if plan_source == PlanSource.ACTUAL else None
    actual_rows = _sum_actual_rows(runtime_info)
    actual_duration_ms = _max_actual_duration_ms(runtime_info)

    node_warnings = _extract_warnings(rel_op_elem, node_id)
    warnings_out.extend(node_warnings)

    children_elems = _direct_child_rel_ops(rel_op_elem)
    children = [
        _build_operator_tree(child, total_cost, plan_source, counter, warnings_out) for child in children_elems
    ]

    return Operator(
        id=node_id,
        operator_type=_map_operator_type(physical_op, logical_op, is_lookup),
        physical_op_raw=physical_op,
        object_ref=_extract_object_ref(wrapper),
        estimated_rows=estimated_rows,
        actual_rows=actual_rows,
        row_estimate_ratio=_compute_row_estimate_ratio(estimated_rows, actual_rows),
        estimated_cost=estimated_cost,
        estimated_cost_pct_of_total=_compute_cost_pct(estimated_cost, total_cost),
        actual_duration_ms=actual_duration_ms,
        predicates=_extract_predicates(wrapper),
        join_type=_map_join_type(physical_op, logical_op),
        access_type=_map_access_type(physical_op, is_lookup),
        sort_present=wrapper is not None and etree.QName(wrapper).localname == "Sort",
        parallel=rel_op_elem.get("Parallel") == "1",
        memory_grant_kb=None,
        tempdb_spill=any(w.type == WarningType.TEMPDB_SPILL for w in node_warnings),
        children=children,
    )


def _direct_child_rel_ops(elem) -> list:
    """This node's immediate RelOp children, wherever they sit (direct sibling
    of the detail wrapper or nested inside it) -- stops descending the moment a
    RelOp is found, so it never reaches into a child operator's own subtree.
    Avoids hardcoding every one of SQL Server's wrapper element shapes."""
    result = []
    for child in elem:
        if etree.QName(child).localname == "RelOp":
            result.append(child)
        else:
            result.extend(_direct_child_rel_ops(child))
    return result


def _find_detail_wrapper(rel_op_elem):
    for child in rel_op_elem:
        if etree.QName(child).localname not in _NON_WRAPPER_TAGS:
            return child
    return None


def _map_operator_type(physical_op: str, logical_op: str, is_lookup: bool) -> OperatorType:
    if is_lookup and physical_op in LOOKUP_CAPABLE_PHYSICAL_OPS:
        return OperatorType.BOOKMARK_LOOKUP
    if physical_op == "Hash Match":
        return HASH_MATCH_LOGICAL_OP_MAP.get(logical_op, OperatorType.OTHER)
    mapped = PHYSICAL_OP_MAP.get(physical_op)
    if mapped is not None:
        return mapped
    logger.warning("Unmapped SQL Server PhysicalOp=%r LogicalOp=%r; operator_type=OTHER", physical_op, logical_op)
    return OperatorType.OTHER


def _map_access_type(physical_op: str, is_lookup: bool) -> Optional[AccessType]:
    if is_lookup:
        return AccessType.BOOKMARK_LOOKUP
    if "Seek" in physical_op:
        return AccessType.SEEK
    if physical_op == "Table Scan":
        return AccessType.FULL_SCAN
    if "Scan" in physical_op:
        return AccessType.SCAN
    return None


def _map_join_type(physical_op: str, logical_op: str) -> Optional[JoinType]:
    if physical_op == "Nested Loops":
        return JoinType.NESTED_LOOP
    if physical_op == "Merge Join":
        return JoinType.MERGE
    if physical_op == "Hash Match" and logical_op in HASH_JOIN_LOGICAL_OPS:
        return JoinType.HASH
    return None


def _extract_object_ref(wrapper_elem) -> Optional[ObjectRef]:
    if wrapper_elem is None:
        return None
    obj = wrapper_elem.find(".//sp:Object", NSMAP)
    if obj is None:
        return None
    return ObjectRef(
        schema=_strip_brackets(obj.get("Schema")),
        table=_strip_brackets(obj.get("Table")),
        index=_strip_brackets(obj.get("Index")),
    )


def _extract_predicates(wrapper_elem) -> list[str]:
    if wrapper_elem is None:
        return []
    predicates: list[str] = []
    for scalar_op in wrapper_elem.findall(".//sp:ScalarOperator", NSMAP):
        text = scalar_op.get("ScalarString")
        if text and text not in predicates:
            predicates.append(text)
    return predicates


def _extract_warnings(rel_op_elem, operator_id: str) -> list[Warning]:
    warnings_elem = rel_op_elem.find("sp:Warnings", NSMAP)
    if warnings_elem is None:
        return []
    result = []
    for child in warnings_elem:
        tag = etree.QName(child).localname
        wtype = WARNING_TAG_MAP.get(tag, WarningType.OTHER)
        result.append(Warning(type=wtype, detail=_warning_detail(child), operator_id=operator_id, severity=None))
    return result


def _warning_detail(elem) -> str:
    if elem.attrib:
        return ", ".join(f"{k}={v}" for k, v in elem.attrib.items())
    return etree.QName(elem).localname


def _extract_missing_indexes(query_plan_elem) -> list[MissingIndex]:
    missing_indexes_elem = query_plan_elem.find("sp:MissingIndexes", NSMAP)
    if missing_indexes_elem is None:
        return []
    result = []
    for group in missing_indexes_elem.findall("sp:MissingIndexGroup", NSMAP):
        impact = _get_float(group, "Impact")
        for mi in group.findall("sp:MissingIndex", NSMAP):
            columns_by_usage: dict[str, list[str]] = {"EQUALITY": [], "INEQUALITY": [], "INCLUDE": []}
            for cg in mi.findall("sp:ColumnGroup", NSMAP):
                usage = cg.get("Usage")
                if usage not in columns_by_usage:
                    continue
                columns_by_usage[usage] = [
                    _strip_brackets(c.get("Name")) for c in cg.findall("sp:Column", NSMAP) if c.get("Name")
                ]
            result.append(
                MissingIndex(
                    table=_strip_brackets(mi.get("Table")) or "",
                    columns_equality=columns_by_usage["EQUALITY"],
                    columns_inequality=columns_by_usage["INEQUALITY"],
                    columns_include=columns_by_usage["INCLUDE"],
                    estimated_impact=impact,
                )
            )
    return result


def _sum_actual_rows(runtime_info_elem) -> Optional[float]:
    if runtime_info_elem is None:
        return None
    total = 0.0
    found = False
    for counters in runtime_info_elem.findall("sp:RunTimeCountersPerThread", NSMAP):
        rows = counters.get("ActualRows")
        if rows is not None:
            total += float(rows)
            found = True
    return total if found else None


def _max_actual_duration_ms(runtime_info_elem) -> Optional[float]:
    if runtime_info_elem is None:
        return None
    values = [
        float(v)
        for v in (c.get("ActualElapsedms") for c in runtime_info_elem.findall("sp:RunTimeCountersPerThread", NSMAP))
        if v is not None
    ]
    return max(values) if values else None


def _compute_row_estimate_ratio(estimated: Optional[float], actual: Optional[float]) -> Optional[float]:
    if estimated is None or actual is None or estimated == 0:
        return None
    return actual / estimated


def _compute_cost_pct(node_cost: Optional[float], total_cost: Optional[float]) -> Optional[float]:
    if node_cost is None or total_cost is None or total_cost == 0:
        return None
    return node_cost / total_cost


def _map_statement_type(raw: str) -> StatementType:
    try:
        return StatementType(raw)
    except ValueError:
        return StatementType.OTHER


def _strip_brackets(s: Optional[str]) -> Optional[str]:
    return s.strip("[]") if s is not None else None


def _redact_literals(text: str) -> str:
    """Identity passthrough. Real literal parameterization (sqlglot-based) is
    deferred; this seam exists so the public signature won't need to change
    once that lands."""
    return text


def _get_float(elem, attr: str) -> Optional[float]:
    value = elem.get(attr)
    return float(value) if value is not None else None
