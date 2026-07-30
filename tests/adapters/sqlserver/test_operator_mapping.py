from querysmith.adapters.sqlserver import parse_plan_xml
from querysmith.ir.models import OperatorType, PlanSource

_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<ShowPlanXML xmlns="http://schemas.microsoft.com/sqlserver/2004/07/showplan">
  <BatchSequence>
    <Batch>
      <Statements>
        <StmtSimple StatementText="SELECT 1" StatementType="SELECT" StatementSubTreeCost="1.0">
          <QueryPlan>
            {rel_op}
          </QueryPlan>
        </StmtSimple>
      </Statements>
    </Batch>
  </BatchSequence>
</ShowPlanXML>"""


def _parse(rel_op_xml: str):
    return parse_plan_xml(_TEMPLATE.format(rel_op=rel_op_xml), plan_source=PlanSource.ESTIMATED)


def test_unmapped_operator_falls_back_to_other():
    rel_op = """
    <RelOp NodeId="0" PhysicalOp="Compute Scalar" LogicalOp="Compute Scalar"
           EstimateRows="1" EstimatedTotalSubtreeCost="1.0" Parallel="0">
      <ComputeScalar>
        <DefinedValues />
      </ComputeScalar>
    </RelOp>
    """
    plan = _parse(rel_op)
    assert plan.root_operator.operator_type == OperatorType.OTHER
    assert plan.root_operator.physical_op_raw == "Compute Scalar"


def test_hash_match_disambiguation_join():
    rel_op = """
    <RelOp NodeId="0" PhysicalOp="Hash Match" LogicalOp="Inner Join"
           EstimateRows="1" EstimatedTotalSubtreeCost="1.0" Parallel="0">
      <Hash />
    </RelOp>
    """
    plan = _parse(rel_op)
    assert plan.root_operator.operator_type == OperatorType.JOIN_HASH


def test_hash_match_disambiguation_aggregate():
    rel_op = """
    <RelOp NodeId="0" PhysicalOp="Hash Match" LogicalOp="Aggregate"
           EstimateRows="1" EstimatedTotalSubtreeCost="1.0" Parallel="0">
      <Hash />
    </RelOp>
    """
    plan = _parse(rel_op)
    assert plan.root_operator.operator_type == OperatorType.AGGREGATE


def test_hash_match_unmapped_logical_op_falls_back_to_other():
    rel_op = """
    <RelOp NodeId="0" PhysicalOp="Hash Match" LogicalOp="Union"
           EstimateRows="1" EstimatedTotalSubtreeCost="1.0" Parallel="0">
      <Hash />
    </RelOp>
    """
    plan = _parse(rel_op)
    assert plan.root_operator.operator_type == OperatorType.OTHER


def test_object_ref_and_predicates_scoped_to_own_relop(load_fixture):
    xml = load_fixture("missing_index_suggestion.xml")
    plan = parse_plan_xml(xml, plan_source=PlanSource.ACTUAL)

    root = plan.root_operator
    assert root.object_ref is None
    assert any("CustomerID" in p for p in root.predicates)
    assert not any("Status" in p for p in root.predicates)
    assert not any("OrderDate" in p for p in root.predicates)
