from querysmith.ir.models import Severity
from querysmith.rules import evaluate


def test_parallel_root_flagged_info(op_factory, plan_factory):
    root = op_factory(parallel=True)
    matches = [f for f in evaluate(plan_factory(root)) if f.rule_id == "parallelism_used"]
    assert len(matches) == 1
    assert matches[0].severity == Severity.INFO
    assert matches[0].suggested_fix is None


def test_serial_root_not_flagged(op_factory, plan_factory):
    root = op_factory(parallel=False)
    assert not [f for f in evaluate(plan_factory(root)) if f.rule_id == "parallelism_used"]
