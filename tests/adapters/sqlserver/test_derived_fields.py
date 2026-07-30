from querysmith.adapters.sqlserver import parse_plan_xml
from querysmith.ir.models import PlanSource

_ZERO_ESTIMATE_XML = """<?xml version="1.0" encoding="utf-8"?>
<ShowPlanXML xmlns="http://schemas.microsoft.com/sqlserver/2004/07/showplan">
  <BatchSequence>
    <Batch>
      <Statements>
        <StmtSimple StatementText="SELECT 1" StatementType="SELECT" StatementSubTreeCost="1.0">
          <QueryPlan>
            <RelOp NodeId="0" PhysicalOp="Table Scan" LogicalOp="Table Scan"
                   EstimateRows="0" EstimatedTotalSubtreeCost="1.0" Parallel="0">
              <RunTimeInformation>
                <RunTimeCountersPerThread Thread="0" ActualRows="5" ActualExecutions="1" />
              </RunTimeInformation>
              <TableScan>
                <Object Database="[TestDB]" Schema="[dbo]" Table="[T]" />
              </TableScan>
            </RelOp>
          </QueryPlan>
        </StmtSimple>
      </Statements>
    </Batch>
  </BatchSequence>
</ShowPlanXML>"""


def test_ratio_none_when_plan_source_estimated(load_fixture):
    xml = load_fixture("simple_index_seek.xml")
    plan = parse_plan_xml(xml, plan_source=PlanSource.ESTIMATED)
    assert plan.root_operator.actual_rows is None
    assert plan.root_operator.row_estimate_ratio is None


def test_ratio_none_on_zero_estimate_not_zero_division_error():
    plan = parse_plan_xml(_ZERO_ESTIMATE_XML, plan_source=PlanSource.ACTUAL)
    assert plan.root_operator.estimated_rows == 0
    assert plan.root_operator.actual_rows == 5
    assert plan.root_operator.row_estimate_ratio is None


def test_cost_pct_root_is_always_one(load_fixture):
    xml = load_fixture("tempdb_spill.xml")
    plan = parse_plan_xml(xml, plan_source=PlanSource.ACTUAL)
    assert plan.root_operator.estimated_cost_pct_of_total == 1.0


def test_cost_pct_non_root_matches_literal_fraction(load_fixture):
    xml = load_fixture("tempdb_spill.xml")
    plan = parse_plan_xml(xml, plan_source=PlanSource.ACTUAL)
    aggregate = plan.root_operator.children[0]
    assert aggregate.estimated_cost == 3.1
    assert aggregate.estimated_cost_pct_of_total == 3.1 / 5.2


def test_module_contract():
    import querysmith.adapters.sqlserver.plan_xml_to_ir as module

    assert module.__all__ == ["parse_plan_xml"]
