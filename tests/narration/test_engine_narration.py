from querysmith.narration.engine import DEFAULT_MODEL, get_narration
from querysmith.narration.ollama_client import OllamaClientError
from querysmith.narration.plan_summary import summarize_plan
from querysmith.narration.prompt import build_prompt


def test_module_contract():
    import querysmith.narration.engine as module

    assert module.__all__ == ["get_narration", "DEFAULT_MODEL"]


def _summary(op_factory, plan_factory):
    return summarize_plan(plan_factory(op_factory()))


def test_happy_path_all_model_sourced(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="a"), finding_factory(rule_id="b")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return {
            "overview": "Model overview",
            "findings": [
                {"finding_index": 0, "explanation": "Explains a"},
                {"finding_index": 1, "explanation": "Explains b"},
            ],
        }

    narration = get_narration(findings, summary, client=client)
    assert narration.degraded is False
    assert narration.overview_source == "model"
    assert narration.overview == "Model overview"
    assert [f.explanation_source for f in narration.findings] == ["model", "model"]
    assert [f.rule_id for f in narration.findings] == ["a", "b"]
    assert narration.findings[0].explanation == "Explains a"
    assert narration.findings[1].explanation == "Explains b"


def test_one_missing_finding_falls_back_individually(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="a"), finding_factory(rule_id="b", summary="B summary", detail="B detail")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return {"overview": "Model overview", "findings": [{"finding_index": 0, "explanation": "Explains a"}]}

    narration = get_narration(findings, summary, client=client)
    assert narration.degraded is False
    assert narration.findings[0].explanation_source == "model"
    assert narration.findings[1].explanation_source == "fallback"
    assert narration.findings[1].explanation == "B summary. B detail"


def test_out_of_range_finding_index_ignored(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="a")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return {
            "overview": "ok",
            "findings": [
                {"finding_index": 5, "explanation": "hallucinated"},
                {"finding_index": 0, "explanation": "Explains a"},
            ],
        }

    narration = get_narration(findings, summary, client=client)
    assert len(narration.findings) == 1
    assert narration.findings[0].explanation == "Explains a"


def test_shuffled_response_order_does_not_change_output_order(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="a"), finding_factory(rule_id="b"), finding_factory(rule_id="c")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return {
            "overview": "ok",
            "findings": [
                {"finding_index": 2, "explanation": "c"},
                {"finding_index": 0, "explanation": "a"},
                {"finding_index": 1, "explanation": "b"},
            ],
        }

    narration = get_narration(findings, summary, client=client)
    assert [f.rule_id for f in narration.findings] == ["a", "b", "c"]
    assert [f.explanation for f in narration.findings] == ["a", "b", "c"]


def test_duplicate_finding_index_first_occurrence_wins(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="a")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return {
            "overview": "ok",
            "findings": [
                {"finding_index": 0, "explanation": "first"},
                {"finding_index": 0, "explanation": "second"},
            ],
        }

    narration = get_narration(findings, summary, client=client)
    assert narration.findings[0].explanation == "first"


def test_model_suggested_fix_threaded_through_when_no_tier0_fix(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="large_table_scan")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return {
            "overview": "ok",
            "findings": [
                {"finding_index": 0, "explanation": "explains it", "suggested_fix": "Add a WHERE clause."}
            ],
        }

    narration = get_narration(findings, summary, client=client)
    assert narration.findings[0].suggested_fix == "Add a WHERE clause."


def test_tier0_fix_wins_over_model_fix(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="missing_index_available", suggested_fix="CREATE NONCLUSTERED INDEX ...;")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return {
            "overview": "ok",
            "findings": [
                {"finding_index": 0, "explanation": "explains it", "suggested_fix": "Model's competing suggestion"}
            ],
        }

    narration = get_narration(findings, summary, client=client)
    assert narration.findings[0].suggested_fix is None


def test_missing_or_null_suggested_fix_not_fabricated(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="cardinality_skew")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return {
            "overview": "ok",
            "findings": [{"finding_index": 0, "explanation": "explains it", "suggested_fix": None}],
        }

    narration = get_narration(findings, summary, client=client)
    assert narration.findings[0].suggested_fix is None


def test_client_error_fully_degrades(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="a", summary="A summary", detail="A detail")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        raise OllamaClientError("connection refused")

    narration = get_narration(findings, summary, client=client)
    assert narration.degraded is True
    assert narration.degraded_reason.startswith("client_error")
    assert narration.overview_source == "fallback"
    assert narration.findings[0].explanation_source == "fallback"
    assert narration.findings[0].explanation == "A summary. A detail"


def test_valid_overview_but_no_findings_key_not_degraded(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="a")]
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return {"overview": "Model overview"}

    narration = get_narration(findings, summary, client=client)
    assert narration.overview_source == "model"
    assert narration.findings[0].explanation_source == "fallback"
    assert narration.degraded is False


def test_empty_findings_list(op_factory, plan_factory):
    summary = _summary(op_factory, plan_factory)

    def client(prompt, model):
        return {"overview": "ok", "findings": []}

    narration = get_narration([], summary, client=client)
    assert narration.findings == []
    assert narration.degraded is False


def test_default_model_and_client_used_when_not_overridden(monkeypatch, op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="a")]
    summary = _summary(op_factory, plan_factory)
    captured = {}

    def fake_generate_json(prompt, model):
        captured["model"] = model
        return {"overview": "ok", "findings": []}

    monkeypatch.setattr("querysmith.narration.engine.generate_json", fake_generate_json)
    narration = get_narration(findings, summary)
    assert captured["model"] == DEFAULT_MODEL
    assert narration.model_name == DEFAULT_MODEL


def test_prompt_sent_matches_build_prompt(op_factory, plan_factory, finding_factory):
    findings = [finding_factory(rule_id="a")]
    summary = _summary(op_factory, plan_factory)
    captured = {}

    def client(prompt, model):
        captured["prompt"] = prompt
        return {"overview": "ok", "findings": []}

    get_narration(findings, summary, client=client)
    assert captured["prompt"] == build_prompt(summary, findings)
