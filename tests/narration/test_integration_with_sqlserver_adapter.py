import pathlib

from querysmith.adapters.sqlserver import parse_plan_xml
from querysmith.ir.models import PlanSource
from querysmith.narration import get_narration, summarize_plan
from querysmith.rules import evaluate

FIXTURES_DIR = pathlib.Path(__file__).parent.parent / "fixtures" / "sqlserver"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_full_pipeline_wires_together():
    plan = parse_plan_xml(_load("tempdb_spill.xml"), plan_source=PlanSource.ACTUAL)
    findings = evaluate(plan)
    summary = summarize_plan(plan)

    def fake_client(prompt, model):
        return {
            "overview": "This plan spills to tempdb during the sort.",
            "findings": [
                {"finding_index": i, "explanation": f"Explains {f.rule_id}"} for i, f in enumerate(findings)
            ],
        }

    narration = get_narration(findings, summary, client=fake_client)

    assert narration.degraded is False
    assert [fn.rule_id for fn in narration.findings] == [f.rule_id for f in findings]
    assert [fn.severity for fn in narration.findings] == [f.severity for f in findings]
    assert all(fn.explanation_source == "model" for fn in narration.findings)


def test_full_pipeline_with_no_findings_still_produces_narration():
    plan = parse_plan_xml(_load("simple_index_seek.xml"), plan_source=PlanSource.ACTUAL)
    findings = evaluate(plan)
    assert findings == []
    summary = summarize_plan(plan)

    def fake_client(prompt, model):
        return {"overview": "Healthy plan, no issues found.", "findings": []}

    narration = get_narration(findings, summary, client=fake_client)
    assert narration.findings == []
    assert narration.overview == "Healthy plan, no issues found."
    assert narration.degraded is False
