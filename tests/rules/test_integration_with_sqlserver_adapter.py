import pathlib

from querysmith.adapters.sqlserver import parse_plan_xml
from querysmith.ir.models import PlanSource, Severity
from querysmith.rules import evaluate

FIXTURES_DIR = pathlib.Path(__file__).parent.parent / "fixtures" / "sqlserver"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_large_table_scan_fixture_flags_scan_and_no_stats():
    plan = parse_plan_xml(_load("large_table_scan.xml"), plan_source=PlanSource.ACTUAL)
    findings = evaluate(plan)
    rule_ids = {f.rule_id for f in findings}
    assert "large_table_scan" in rule_ids
    assert "adapter_warning.column_with_no_stats" in rule_ids
    scan_finding = next(f for f in findings if f.rule_id == "large_table_scan")
    assert scan_finding.severity == Severity.CRITICAL  # 500,000 actual rows


def test_missing_index_suggestion_fixture_flags_lookup_and_missing_index():
    plan = parse_plan_xml(_load("missing_index_suggestion.xml"), plan_source=PlanSource.ACTUAL)
    findings = evaluate(plan)
    rule_ids = {f.rule_id for f in findings}
    assert "non_covering_key_lookup" in rule_ids
    assert "missing_index_available" in rule_ids
    mi_finding = next(f for f in findings if f.rule_id == "missing_index_available")
    assert mi_finding.severity == Severity.CRITICAL  # impact 87.6


def test_tempdb_spill_fixture_flags_spill_critical():
    plan = parse_plan_xml(_load("tempdb_spill.xml"), plan_source=PlanSource.ACTUAL)
    findings = evaluate(plan)
    spill = next(f for f in findings if f.rule_id == "adapter_warning.tempdb_spill")
    assert spill.severity == Severity.CRITICAL
    assert findings[0] is spill  # critical sorts first


def test_simple_index_seek_fixture_has_no_critical_or_warning_findings():
    plan = parse_plan_xml(_load("simple_index_seek.xml"), plan_source=PlanSource.ACTUAL)
    findings = evaluate(plan)
    assert not [f for f in findings if f.severity in (Severity.CRITICAL, Severity.WARNING)]
