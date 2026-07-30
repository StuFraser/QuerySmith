from querysmith.ir.models import MissingIndex, Severity
from querysmith.rules import evaluate


def test_high_impact_missing_index_critical(op_factory, plan_factory):
    mi = MissingIndex(table="Orders", columns_equality=["Status"], estimated_impact=90.0)
    findings = [f for f in evaluate(plan_factory(op_factory(), missing_indexes=[mi])) if f.rule_id == "missing_index_available"]
    assert len(findings) == 1
    assert findings[0].severity == Severity.CRITICAL


def test_moderate_impact_missing_index_warning(op_factory, plan_factory):
    mi = MissingIndex(table="Orders", estimated_impact=60.0)
    findings = evaluate(plan_factory(op_factory(), missing_indexes=[mi]))
    assert [f for f in findings if f.rule_id == "missing_index_available"][0].severity == Severity.WARNING


def test_low_impact_missing_index_info(op_factory, plan_factory):
    mi = MissingIndex(table="Orders", estimated_impact=10.0)
    findings = evaluate(plan_factory(op_factory(), missing_indexes=[mi]))
    assert [f for f in findings if f.rule_id == "missing_index_available"][0].severity == Severity.INFO


def test_no_impact_value_defaults_info(op_factory, plan_factory):
    mi = MissingIndex(table="Orders", estimated_impact=None)
    findings = evaluate(plan_factory(op_factory(), missing_indexes=[mi]))
    assert [f for f in findings if f.rule_id == "missing_index_available"][0].severity == Severity.INFO
