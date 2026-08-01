import pytest

from querysmith.ir.models import (
    AccessType,
    Engine,
    IRPlan,
    ObjectType,
    Operator,
    OperatorType,
    PlanMeta,
    PlanSource,
    Severity,
    Statement,
    StatementType,
)
from querysmith.rules.models import Finding


def make_operator(
    id="0",
    operator_type=OperatorType.INDEX_SEEK,
    physical_op_raw="Index Seek",
    access_type=AccessType.SEEK,
    estimated_rows=None,
    actual_rows=None,
    row_estimate_ratio=None,
    estimated_cost_pct_of_total=None,
    actual_duration_ms=None,
    parallel=False,
    tempdb_spill=False,
    object_ref=None,
    predicates=None,
    children=None,
):
    return Operator(
        id=id,
        operator_type=operator_type,
        physical_op_raw=physical_op_raw,
        access_type=access_type,
        estimated_rows=estimated_rows,
        actual_rows=actual_rows,
        row_estimate_ratio=row_estimate_ratio,
        estimated_cost_pct_of_total=estimated_cost_pct_of_total,
        actual_duration_ms=actual_duration_ms,
        parallel=parallel,
        tempdb_spill=tempdb_spill,
        object_ref=object_ref,
        predicates=predicates or [],
        children=children or [],
    )


def make_plan(root_operator, warnings=None, missing_indexes=None, statement_text="SELECT 1"):
    return IRPlan(
        meta=PlanMeta(
            engine=Engine.SQLSERVER,
            engine_version=None,
            plan_source=PlanSource.ACTUAL,
            captured_at=None,
            object_type=ObjectType.ADHOC_QUERY,
            object_name=None,
            database_name="TestDB",
        ),
        statement=Statement(text=statement_text, statement_type=StatementType.SELECT),
        root_operator=root_operator,
        warnings=warnings or [],
        missing_indexes=missing_indexes or [],
    )


def make_finding(
    rule_id="large_table_scan",
    severity=Severity.WARNING,
    operator_id="0",
    summary="Summary",
    detail="Detail",
    suggested_fix=None,
):
    return Finding(
        rule_id=rule_id,
        severity=severity,
        operator_id=operator_id,
        summary=summary,
        detail=detail,
        suggested_fix=suggested_fix,
    )


@pytest.fixture
def op_factory():
    return make_operator


@pytest.fixture
def plan_factory():
    return make_plan


@pytest.fixture
def finding_factory():
    return make_finding
