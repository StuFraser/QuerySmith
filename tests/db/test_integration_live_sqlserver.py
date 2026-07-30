"""Real end-to-end smoke test against a live SQL Server instance. Skipped
unless QUERYSMITH_SQLSERVER_INTEGRATION=1 and QUERYSMITH_TEST_DB_* env vars
are set -- a plain `pytest -v` run requires zero network access.
"""

import os

import pytest

from querysmith.adapters.sqlserver import parse_plan_xml
from querysmith.db import capture_plan_xml
from querysmith.ir.models import PlanSource
from querysmith.rules import evaluate

_ENABLED = os.environ.get("QUERYSMITH_SQLSERVER_INTEGRATION") == "1"


@pytest.mark.skipif(not _ENABLED, reason="QUERYSMITH_SQLSERVER_INTEGRATION not set")
def test_capture_and_evaluate_against_live_sqlserver():
    xml = capture_plan_xml(
        server=os.environ["QUERYSMITH_TEST_DB_SERVER"],
        database=os.environ["QUERYSMITH_TEST_DB_DATABASE"],
        user=os.environ["QUERYSMITH_TEST_DB_USER"],
        password=os.environ["QUERYSMITH_DB_PASSWORD"],
        query=os.environ.get("QUERYSMITH_TEST_DB_QUERY", "SELECT * FROM dbo.QuerySmith_test1"),
    )
    plan = parse_plan_xml(xml, plan_source=PlanSource.ACTUAL)
    findings = evaluate(plan)
    assert findings  # this fixture view is known to have plan issues
