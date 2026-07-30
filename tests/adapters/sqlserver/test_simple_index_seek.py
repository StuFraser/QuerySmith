from querysmith.adapters.sqlserver import parse_plan_xml
from querysmith.ir.models import AccessType, OperatorType, PlanSource, StatementType


def test_simple_index_seek(load_fixture):
    xml = load_fixture("simple_index_seek.xml")
    plan = parse_plan_xml(xml, plan_source=PlanSource.ACTUAL)

    root = plan.root_operator
    assert root.operator_type == OperatorType.INDEX_SEEK
    assert root.physical_op_raw == "Index Seek"
    assert root.access_type == AccessType.SEEK
    assert root.object_ref is not None
    assert root.object_ref.schema == "dbo"
    assert root.object_ref.table == "Orders"
    assert root.object_ref.index == "IX_Orders_CustomerID"
    assert any("CustomerID" in p for p in root.predicates)
    assert root.row_estimate_ratio == 1.0
    assert root.estimated_cost_pct_of_total == 1.0
    assert root.memory_grant_kb == 1024
    assert root.tempdb_spill is False
    assert plan.warnings == []
    assert plan.missing_indexes == []
    assert plan.statement.statement_type == StatementType.SELECT
