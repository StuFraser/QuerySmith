from querysmith.ir.models import Severity, Warning, WarningType
from querysmith.rules import evaluate


def test_tempdb_spill_promoted_to_critical(op_factory, plan_factory):
    plan = plan_factory(
        op_factory(),
        warnings=[Warning(type=WarningType.TEMPDB_SPILL, detail="SpillLevel=1", operator_id="0")],
    )
    matches = [f for f in evaluate(plan) if f.rule_id == "adapter_warning.tempdb_spill"]
    assert len(matches) == 1
    assert matches[0].severity == Severity.CRITICAL
    assert matches[0].operator_id == "0"


def test_no_join_predicate_promoted_to_critical(op_factory, plan_factory):
    plan = plan_factory(
        op_factory(),
        warnings=[Warning(type=WarningType.NO_JOIN_PREDICATE, detail="", operator_id="0")],
    )
    findings = evaluate(plan)
    assert findings[0].severity == Severity.CRITICAL


def test_implicit_conversion_promoted_to_warning(op_factory, plan_factory):
    plan = plan_factory(
        op_factory(),
        warnings=[Warning(type=WarningType.IMPLICIT_CONVERSION, detail="", operator_id="0")],
    )
    findings = evaluate(plan)
    assert findings[0].severity == Severity.WARNING


def test_unknown_adapter_warning_promoted_to_info(op_factory, plan_factory):
    plan = plan_factory(
        op_factory(),
        warnings=[Warning(type=WarningType.OTHER, detail="mystery", operator_id="0")],
    )
    findings = evaluate(plan)
    assert findings[0].severity == Severity.INFO
