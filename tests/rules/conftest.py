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
    Statement,
    StatementType,
)


def make_operator(
    id="0",
    operator_type=OperatorType.INDEX_SEEK,
    physical_op_raw="Index Seek",
    access_type=AccessType.SEEK,
    estimated_rows=None,
    actual_rows=None,
    row_estimate_ratio=None,
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
        parallel=parallel,
        tempdb_spill=tempdb_spill,
        object_ref=object_ref,
        predicates=predicates or [],
        children=children or [],
    )


def make_plan(root_operator, warnings=None, missing_indexes=None):
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
        statement=Statement(text="SELECT 1", statement_type=StatementType.SELECT),
        root_operator=root_operator,
        warnings=warnings or [],
        missing_indexes=missing_indexes or [],
    )


@pytest.fixture
def op_factory():
    return make_operator


@pytest.fixture
def plan_factory():
    return make_plan
