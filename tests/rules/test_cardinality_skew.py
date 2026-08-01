from querysmith.rules import evaluate
from querysmith.ir.models import Severity


def test_underestimate_flagged(op_factory, plan_factory):
    root = op_factory(row_estimate_ratio=50.0)
    matches = [f for f in evaluate(plan_factory(root)) if f.rule_id == "cardinality_skew"]
    assert len(matches) == 1
    assert matches[0].severity == Severity.WARNING
    assert matches[0].suggested_fix is None


def test_overestimate_flagged(op_factory, plan_factory):
    root = op_factory(row_estimate_ratio=0.01)
    assert len([f for f in evaluate(plan_factory(root)) if f.rule_id == "cardinality_skew"]) == 1


def test_close_ratio_not_flagged(op_factory, plan_factory):
    root = op_factory(row_estimate_ratio=1.2)
    assert not [f for f in evaluate(plan_factory(root)) if f.rule_id == "cardinality_skew"]


def test_none_ratio_not_flagged(op_factory, plan_factory):
    root = op_factory(row_estimate_ratio=None)
    assert not [f for f in evaluate(plan_factory(root)) if f.rule_id == "cardinality_skew"]
