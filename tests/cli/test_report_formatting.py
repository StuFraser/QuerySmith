from querysmith.cli import format_report
from querysmith.ir.models import Severity
from querysmith.narration.models import FindingNarration, Narration, PlanSummary
from querysmith.rules.models import Finding


def _summary(**overrides):
    defaults = dict(
        engine="sqlserver",
        engine_version=None,
        database_name="TestDB",
        object_type="adhoc_query",
        object_name=None,
        plan_source="actual",
        statement_type="SELECT",
        statement_text="SELECT 1",
        total_estimated_cost=1.0,
        total_actual_duration_ms=10.0,
        total_actual_rows=5,
        operator_count=1,
        notable_operators=[],
    )
    defaults.update(overrides)
    return PlanSummary(**defaults)


def _finding(**overrides):
    defaults = dict(
        rule_id="large_table_scan", severity=Severity.WARNING, operator_id="0", summary="Big scan", detail="detail"
    )
    defaults.update(overrides)
    return Finding(**defaults)


def test_zero_findings():
    report = format_report(_summary(), [], None)
    assert "Findings (0)" in report
    assert "No issues found" in report


def test_findings_with_model_narration():
    findings = [_finding()]
    narration = Narration(
        overview="Overview text",
        overview_source="model",
        findings=[
            FindingNarration(
                rule_id="large_table_scan",
                severity=Severity.WARNING,
                operator_id="0",
                summary="Big scan",
                detail="detail",
                explanation="Model explanation",
                explanation_source="model",
            )
        ],
        degraded=False,
        degraded_reason=None,
        model_name="llama3.2:3b",
    )
    report = format_report(_summary(), findings, narration)
    assert "Findings (1)" in report
    assert "Model explanation" in report
    assert "Overview text" in report
    assert "degraded" not in report.lower()


def test_findings_with_narration_disabled():
    report = format_report(_summary(), [_finding()], None)
    assert "narration disabled" in report.lower()


def test_degraded_narration_shows_reason():
    narration = Narration(
        overview="Fallback overview",
        overview_source="fallback",
        findings=[],
        degraded=True,
        degraded_reason="client_error: connection refused",
        model_name="llama3.2:3b",
    )
    report = format_report(_summary(), [], narration)
    assert "[Tier 1 narration degraded: client_error: connection refused]" in report
