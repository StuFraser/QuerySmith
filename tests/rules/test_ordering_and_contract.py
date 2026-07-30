from querysmith.ir.models import Severity, Warning, WarningType
from querysmith.rules import evaluate


def test_findings_sorted_critical_first(op_factory, plan_factory):
    root = op_factory(parallel=True)  # INFO
    plan = plan_factory(
        root,
        warnings=[Warning(type=WarningType.TEMPDB_SPILL, detail="", operator_id="0")],  # CRITICAL
    )
    order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}
    severities = [f.severity for f in evaluate(plan)]
    assert severities == sorted(severities, key=lambda s: order[s])


def test_module_contract():
    import querysmith.rules.engine as module

    assert module.__all__ == ["evaluate"]
