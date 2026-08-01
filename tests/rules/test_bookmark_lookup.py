from querysmith.ir.models import AccessType, ObjectRef, OperatorType, Severity
from querysmith.rules import evaluate


def test_bookmark_lookup_flagged(op_factory, plan_factory):
    root = op_factory(
        operator_type=OperatorType.BOOKMARK_LOOKUP,
        access_type=AccessType.BOOKMARK_LOOKUP,
        object_ref=ObjectRef(schema="dbo", table="Orders", index="PK_Orders"),
    )
    matches = [f for f in evaluate(plan_factory(root)) if f.rule_id == "non_covering_key_lookup"]
    assert len(matches) == 1
    assert matches[0].severity == Severity.WARNING
    assert "Orders" in matches[0].summary
    assert matches[0].suggested_fix is None


def test_regular_seek_not_flagged(op_factory, plan_factory):
    assert not [f for f in evaluate(plan_factory(op_factory())) if f.rule_id == "non_covering_key_lookup"]
