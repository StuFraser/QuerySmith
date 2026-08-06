from querysmith.narration.fix_engine import propose_fixes
from querysmith.narration.ollama_client import OllamaClientError
from querysmith.narration.plan_summary import summarize_plan


def test_module_contract():
    import querysmith.narration.fix_engine as module

    assert module.__all__ == ["propose_fixes"]


def _summary(op_factory, plan_factory):
    return summarize_plan(plan_factory(op_factory()))


def test_rewritten_query_and_index_script_both_kept_when_valid(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="no_join_predicate")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return {
            "fixes": [
                {
                    "finding_index": 0,
                    "rewritten_query": "SELECT a.Id FROM dbo.A a JOIN dbo.B b ON a.Id = b.AId",
                    "index_script": "CREATE INDEX IX_A ON dbo.A (Id);",
                }
            ]
        }

    proposal = propose_fixes(findings, summary, client=client)
    assert proposal.degraded is False
    assert len(proposal.fixes) == 1
    fix = proposal.fixes[0]
    assert fix.finding_index == 0
    assert fix.rewritten_query == "SELECT a.Id FROM dbo.A a JOIN dbo.B b ON a.Id = b.AId"
    assert fix.index_script == "CREATE INDEX IX_A ON dbo.A (Id);"


def test_invalid_rewritten_query_dropped_but_index_script_kept(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="no_join_predicate")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return {
            "fixes": [
                {
                    "finding_index": 0,
                    "rewritten_query": "DROP TABLE dbo.A; SELECT 1;",
                    "index_script": "CREATE INDEX IX_A ON dbo.A (Id);",
                }
            ]
        }

    proposal = propose_fixes(findings, summary, client=client)
    assert len(proposal.fixes) == 1
    assert proposal.fixes[0].rewritten_query is None
    assert proposal.fixes[0].index_script == "CREATE INDEX IX_A ON dbo.A (Id);"


def test_invalid_index_script_dropped_but_rewritten_query_kept(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="no_join_predicate")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return {
            "fixes": [
                {
                    "finding_index": 0,
                    "rewritten_query": "SELECT 1",
                    "index_script": "SELECT * FROM dbo.A",  # not a CREATE INDEX
                }
            ]
        }

    proposal = propose_fixes(findings, summary, client=client)
    assert len(proposal.fixes) == 1
    assert proposal.fixes[0].rewritten_query == "SELECT 1"
    assert proposal.fixes[0].index_script is None


def test_finding_with_tier0_fix_never_gets_a_model_fix(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="missing_index_available", suggested_fix="CREATE NONCLUSTERED INDEX ...;")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return {
            "fixes": [
                {"finding_index": 0, "rewritten_query": "SELECT 1", "index_script": "CREATE INDEX IX_A ON dbo.A (Id);"}
            ]
        }

    proposal = propose_fixes(findings, summary, client=client)
    assert proposal.fixes == []


def test_out_of_range_finding_index_ignored(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="a")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return {"fixes": [{"finding_index": 5, "rewritten_query": "SELECT 1"}]}

    proposal = propose_fixes(findings, summary, client=client)
    assert proposal.fixes == []


def test_no_fixes_proposed_is_not_degraded(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="a")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return {"fixes": [{"finding_index": 0, "rewritten_query": None, "index_script": None}]}

    proposal = propose_fixes(findings, summary, client=client)
    assert proposal.degraded is False
    assert proposal.fixes == []


def test_client_error_degrades(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="a")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        raise OllamaClientError("connection refused")

    proposal = propose_fixes(findings, summary, client=client)
    assert proposal.degraded is True
    assert proposal.degraded_reason.startswith("client_error")
    assert proposal.fixes == []


def test_invalid_response_shape_degrades(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="a")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return "not a dict"

    proposal = propose_fixes(findings, summary, client=client)
    assert proposal.degraded is True
    assert proposal.degraded_reason == "invalid_response_shape"


def test_model_name_threaded_through(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="a")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return {"fixes": []}

    proposal = propose_fixes(findings, summary, model="custom-model", client=client)
    assert proposal.model_name == "custom-model"
