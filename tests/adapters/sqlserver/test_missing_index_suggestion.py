from querysmith.adapters.sqlserver import parse_plan_xml
from querysmith.ir.models import AccessType, JoinType, OperatorType, PlanSource


def _count_nodes(op):
    return 1 + sum(_count_nodes(c) for c in op.children)


def _walk(op):
    yield op
    for child in op.children:
        yield from _walk(child)


def test_missing_index_suggestion(load_fixture):
    xml = load_fixture("missing_index_suggestion.xml")
    plan = parse_plan_xml(xml, plan_source=PlanSource.ACTUAL)

    assert len(plan.missing_indexes) == 1
    missing_index = plan.missing_indexes[0]
    assert missing_index.columns_equality == ["Status"]
    assert missing_index.columns_inequality == ["OrderDate"]
    assert missing_index.columns_include == ["OrderID"]
    assert missing_index.estimated_impact == 87.6

    root = plan.root_operator
    assert _count_nodes(root) == 5

    nodes = list(_walk(root))

    lookups = [n for n in nodes if n.operator_type == OperatorType.BOOKMARK_LOOKUP]
    assert len(lookups) == 1
    assert lookups[0].access_type == AccessType.BOOKMARK_LOOKUP
    assert any("Status" in p for p in lookups[0].predicates)
    assert any("OrderDate" in p for p in lookups[0].predicates)

    joins = [n for n in nodes if n.operator_type == OperatorType.JOIN_NESTED_LOOP]
    assert len(joins) == 2
    assert all(n.join_type == JoinType.NESTED_LOOP for n in joins)

    seeks = [n for n in nodes if n.operator_type == OperatorType.INDEX_SEEK]
    assert len(seeks) == 2
