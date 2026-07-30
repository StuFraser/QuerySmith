from querysmith.adapters.sqlserver import parse_plan_xml
from querysmith.ir.models import AccessType, OperatorType, PlanSource, WarningType


def test_large_table_scan(load_fixture):
    xml = load_fixture("large_table_scan.xml")
    plan = parse_plan_xml(xml, plan_source=PlanSource.ACTUAL)

    root = plan.root_operator
    assert root.operator_type == OperatorType.TABLE_SCAN
    assert root.access_type == AccessType.FULL_SCAN
    assert root.object_ref is not None
    assert root.object_ref.index is None
    assert root.parallel is True
    assert root.row_estimate_ratio == 500000 / 50
    assert root.memory_grant_kb is None

    assert len(plan.warnings) == 1
    warning = plan.warnings[0]
    assert warning.type == WarningType.COLUMN_WITH_NO_STATS
    assert warning.operator_id == root.id
