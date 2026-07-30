from querysmith.adapters.sqlserver import parse_plan_xml
from querysmith.ir.models import OperatorType, PlanSource, WarningType


def test_tempdb_spill(load_fixture):
    xml = load_fixture("tempdb_spill.xml")
    plan = parse_plan_xml(xml, plan_source=PlanSource.ACTUAL)

    root = plan.root_operator
    assert root.operator_type == OperatorType.SORT
    assert root.tempdb_spill is True
    assert root.join_type is None
    assert root.memory_grant_kb == 16384
    assert len(root.children) == 1

    aggregate = root.children[0]
    assert aggregate.operator_type == OperatorType.AGGREGATE
    assert aggregate.tempdb_spill is False
    assert aggregate.join_type is None
    assert len(aggregate.children) == 1

    scan = aggregate.children[0]
    assert scan.operator_type == OperatorType.INDEX_SCAN
    assert scan.tempdb_spill is False
    assert scan.join_type is None
    assert scan.children == []

    spill_warnings = [w for w in plan.warnings if w.type == WarningType.TEMPDB_SPILL]
    assert len(spill_warnings) == 1
    assert spill_warnings[0].operator_id == root.id
