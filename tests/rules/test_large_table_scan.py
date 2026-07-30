from querysmith.ir.models import AccessType, OperatorType, Severity
from querysmith.rules import evaluate


def test_large_scan_flagged_warning(op_factory, plan_factory):
    root = op_factory(operator_type=OperatorType.TABLE_SCAN, access_type=AccessType.FULL_SCAN, actual_rows=50_000)
    matches = [f for f in evaluate(plan_factory(root)) if f.rule_id == "large_table_scan"]
    assert len(matches) == 1
    assert matches[0].severity == Severity.WARNING


def test_very_large_scan_flagged_critical(op_factory, plan_factory):
    root = op_factory(operator_type=OperatorType.TABLE_SCAN, access_type=AccessType.FULL_SCAN, actual_rows=500_000)
    matches = [f for f in evaluate(plan_factory(root)) if f.rule_id == "large_table_scan"]
    assert matches[0].severity == Severity.CRITICAL


def test_small_scan_not_flagged(op_factory, plan_factory):
    root = op_factory(operator_type=OperatorType.TABLE_SCAN, access_type=AccessType.FULL_SCAN, actual_rows=10)
    assert not [f for f in evaluate(plan_factory(root)) if f.rule_id == "large_table_scan"]


def test_seek_never_flagged_regardless_of_row_count(op_factory, plan_factory):
    root = op_factory(operator_type=OperatorType.INDEX_SEEK, access_type=AccessType.SEEK, actual_rows=1_000_000)
    assert not [f for f in evaluate(plan_factory(root)) if f.rule_id == "large_table_scan"]


def test_falls_back_to_estimated_rows_when_actual_absent(op_factory, plan_factory):
    root = op_factory(
        operator_type=OperatorType.TABLE_SCAN,
        access_type=AccessType.FULL_SCAN,
        estimated_rows=200_000,
        actual_rows=None,
    )
    matches = [f for f in evaluate(plan_factory(root)) if f.rule_id == "large_table_scan"]
    assert len(matches) == 1
    assert matches[0].severity == Severity.CRITICAL
