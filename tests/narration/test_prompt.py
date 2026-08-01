from querysmith.narration.plan_summary import summarize_plan
from querysmith.narration.prompt import build_prompt


def test_module_contract():
    import querysmith.narration.prompt as module

    assert module.__all__ == ["build_prompt"]


def test_prompt_contains_plan_summary_fields(op_factory, plan_factory, finding_factory):
    plan = plan_factory(op_factory(), statement_text="SELECT * FROM dbo.Orders")
    summary = summarize_plan(plan)
    prompt = build_prompt(summary, [])
    assert "TestDB" in prompt
    assert "SELECT * FROM dbo.Orders" in prompt


def test_prompt_contains_finding_index_and_fields(finding_factory):
    findings = [
        finding_factory(rule_id="large_table_scan", summary="Big scan"),
        finding_factory(rule_id="cardinality_skew", summary="Skewed"),
    ]
    prompt = build_prompt(_dummy_summary(), findings)
    assert '"finding_index": 0' in prompt
    assert '"finding_index": 1' in prompt
    assert "large_table_scan" in prompt
    assert "cardinality_skew" in prompt
    assert "Big scan" in prompt
    assert "Skewed" in prompt


def test_prompt_contains_schema_instructions():
    prompt = build_prompt(_dummy_summary(), [])
    assert "overview" in prompt
    assert "finding_index" in prompt
    assert "explanation" in prompt
    assert "suggested_fix" in prompt


def test_prompt_includes_tier0_suggested_fix_when_present(finding_factory):
    findings = [finding_factory(suggested_fix="CREATE NONCLUSTERED INDEX [IX_Orders_Status] ON [Orders] ([Status]);")]
    prompt = build_prompt(_dummy_summary(), findings)
    assert "CREATE NONCLUSTERED INDEX" in prompt


def test_prompt_null_suggested_fix_when_absent(finding_factory):
    findings = [finding_factory(suggested_fix=None)]
    prompt = build_prompt(_dummy_summary(), findings)
    assert '"suggested_fix": null' in prompt


def test_prompt_is_deterministic(finding_factory):
    findings = [finding_factory()]
    summary = _dummy_summary()
    assert build_prompt(summary, findings) == build_prompt(summary, findings)


def _dummy_summary():
    from querysmith.narration.models import PlanSummary

    return PlanSummary(
        engine="sqlserver",
        engine_version=None,
        database_name="TestDB",
        object_type="adhoc_query",
        object_name=None,
        plan_source="actual",
        statement_type="SELECT",
        statement_text="SELECT 1",
        total_estimated_cost=1.0,
        total_actual_duration_ms=1.0,
        total_actual_rows=1,
        operator_count=1,
        notable_operators=[],
    )
