from querysmith.ir.models import ObjectRef
from querysmith.narration.plan_summary import summarize_plan


def test_module_contract():
    import querysmith.narration.plan_summary as module

    assert module.__all__ == ["summarize_plan"]


def test_meta_and_statement_fields_copied(op_factory, plan_factory):
    plan = plan_factory(op_factory(), statement_text="SELECT 1")
    summary = summarize_plan(plan)
    assert summary.engine == "sqlserver"
    assert summary.database_name == "TestDB"
    assert summary.statement_type == "SELECT"
    assert summary.statement_text == "SELECT 1"
    assert summary.operator_count == 1


def test_statement_text_truncated_past_limit(op_factory, plan_factory):
    plan = plan_factory(op_factory(), statement_text="SELECT " + "x" * 100)
    summary = summarize_plan(plan, max_statement_text_chars=20)
    assert len(summary.statement_text) == 20 + len(" ...[truncated]")
    assert summary.statement_text.endswith(" ...[truncated]")


def test_statement_text_not_truncated_under_limit(op_factory, plan_factory):
    plan = plan_factory(op_factory(), statement_text="SELECT 1")
    summary = summarize_plan(plan, max_statement_text_chars=1000)
    assert summary.statement_text == "SELECT 1"


def test_notable_operators_capped_and_ranked_by_cost(op_factory, plan_factory):
    leaf = op_factory(id="2", estimated_cost_pct_of_total=0.1)
    mid = op_factory(id="1", estimated_cost_pct_of_total=0.9, children=[leaf])
    root = op_factory(id="0", estimated_cost_pct_of_total=1.0, children=[mid])
    plan = plan_factory(root)

    summary = summarize_plan(plan, max_notable_operators=2)
    assert summary.operator_count == 3
    assert [op.id for op in summary.notable_operators] == ["0", "1"]


def test_notable_operators_tie_broken_by_duration_then_id(op_factory, plan_factory):
    a = op_factory(id="a", estimated_cost_pct_of_total=0.5, actual_duration_ms=10)
    b = op_factory(id="b", estimated_cost_pct_of_total=0.5, actual_duration_ms=20, children=[a])
    root = op_factory(id="root", estimated_cost_pct_of_total=0.5, actual_duration_ms=20, children=[b])
    plan = plan_factory(root)

    summary = summarize_plan(plan, max_notable_operators=3)
    ids = [op.id for op in summary.notable_operators]
    # root and b tie on cost+duration -> id "b" < "root" lexicographically
    assert ids == ["b", "root", "a"]


def test_object_ref_flattened_to_schema_dot_table(op_factory, plan_factory):
    root = op_factory(object_ref=ObjectRef(schema="dbo", table="Orders", index="PK_Orders"))
    plan = plan_factory(root)
    summary = summarize_plan(plan)
    assert summary.notable_operators[0].object_ref == "dbo.Orders"


def test_object_ref_none_when_absent(op_factory, plan_factory):
    plan = plan_factory(op_factory(object_ref=None))
    summary = summarize_plan(plan)
    assert summary.notable_operators[0].object_ref is None
