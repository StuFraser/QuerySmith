"""Live SQL Server plan capture: connects via pyodbc, validates the caller's
query text via query_safety, executes the fixed STATISTICS XML template, and
returns the raw showplan XML string exactly as parse_plan_xml expects (see
design-notes/execution-plan-agent-scope.md). `capture_plan_xml` is the only
public entry point -- callers (the CLI, tests) never construct pyodbc
connections or SQL strings themselves. The statement sent to the server is
always this fixed template; there is no code path that executes unvalidated
text.
"""

from __future__ import annotations

from typing import Callable, Optional

import pyodbc

from querysmith.db.connection import DBCaptureError, DEFAULT_ODBC_DRIVER, connect
from querysmith.db.query_safety import validate_select_only

__all__ = ["capture_plan_xml"]

ConnectFn = Callable[..., pyodbc.Connection]

_STATEMENT_TEMPLATE = "SET STATISTICS XML ON; {query} SET STATISTICS XML OFF;"


def capture_plan_xml(
    *,
    server: str,
    database: str,
    user: str,
    password: str,
    query: str,
    driver: str = DEFAULT_ODBC_DRIVER,
    trust_server_certificate: bool = True,
    timeout_s: float = 60.0,
    connect_fn: Optional[ConnectFn] = None,
) -> str:
    # `connect_fn` defaults to None and is resolved here (not bound as the
    # default parameter value) so tests can monkeypatch the module-level
    # `connect` name -- same late-binding pattern as get_narration's
    # `client=None` -> `generate_json`.
    if connect_fn is None:
        connect_fn = connect

    validated_query = validate_select_only(query)
    query_text = validated_query.strip()
    if not query_text.endswith(";"):
        query_text += ";"
    statement = _STATEMENT_TEMPLATE.format(query=query_text)

    connection = connect_fn(
        server=server,
        database=database,
        user=user,
        password=password,
        driver=driver,
        trust_server_certificate=trust_server_certificate,
        timeout_s=timeout_s,
    )
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(statement)
            xml = _find_showplan_xml(cursor)
        except pyodbc.Error as exc:
            raise DBCaptureError(f"Query execution failed: {exc}") from exc
    finally:
        connection.close()

    if xml is None:
        raise DBCaptureError(
            "No <ShowPlanXML> result set found in query output -- STATISTICS XML "
            "may not have been captured for this statement."
        )
    return xml


def _find_showplan_xml(cursor) -> Optional[str]:
    while True:
        if cursor.description is not None:
            row = cursor.fetchone()
            if (
                row is not None
                and len(row) == 1
                and isinstance(row[0], str)
                and row[0].lstrip().startswith("<ShowPlanXML")
            ):
                return row[0]
        if not cursor.nextset():
            return None
