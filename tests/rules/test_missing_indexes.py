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


def test_suggested_fix_is_create_index_script(op_factory, plan_factory):
    mi = MissingIndex(
        table="Orders",
        columns_equality=["Status"],
        columns_inequality=["OrderDate"],
        columns_include=["OrderID"],
        estimated_impact=90.0,
    )
    findings = evaluate(plan_factory(op_factory(), missing_indexes=[mi]))
    finding = [f for f in findings if f.rule_id == "missing_index_available"][0]
    assert finding.suggested_fix is not None
    assert "CREATE NONCLUSTERED INDEX" in finding.suggested_fix
    assert "[Orders]" in finding.suggested_fix
    assert "[Status]" in finding.suggested_fix
    assert "[OrderDate]" in finding.suggested_fix
    assert "INCLUDE ([OrderID])" in finding.suggested_fix
