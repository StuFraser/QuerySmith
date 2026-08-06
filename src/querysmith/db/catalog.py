"""Live SQL Server catalog listing: connects via pyodbc and lists views in
the target database, following the same fixed-template pattern as
capture.py (see design-notes/execution-plan-web-ui.md, Security section --
the query is never string-built from request input). `list_views` is the
only public entry point.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import pyodbc
import sqlglot
from sqlglot import expressions as exp
from sqlglot.errors import ParseError

from querysmith.db.connection import DBCaptureError, DEFAULT_ODBC_DRIVER, connect
from querysmith.db.query_safety import DIALECT

__all__ = ["list_views", "ViewRef"]

ConnectFn = Callable[..., pyodbc.Connection]

# Fixed, non-user-influenced template -- mirrors capture.py's _STATEMENT_TEMPLATE.
# sys.sql_modules.definition is NULL for WITH ENCRYPTION views; every other
# view has exactly one row here, so an inner join never drops a view.
_LIST_VIEWS_SQL = (
    "SELECT s.name AS schema_name, v.name AS view_name, m.definition AS view_definition "
    "FROM sys.views v "
    "JOIN sys.schemas s ON v.schema_id = s.schema_id "
    "JOIN sys.sql_modules m ON m.object_id = v.object_id "
    "ORDER BY s.name, v.name;"
)


def _extract_select_body(definition: Optional[str]) -> Optional[str]:
    """Best-effort extraction of the SELECT body from a `CREATE VIEW ... AS
    SELECT ...` definition, for pre-filling the query box with something
    more useful than `SELECT * FROM view`. Fails closed to None (caller
    falls back to the SELECT * form) on anything unexpected -- an encrypted
    view's NULL definition, a parse error, or a shape that isn't a plain
    CREATE VIEW wrapping a single SELECT."""
    if not definition:
        return None
    try:
        parsed = sqlglot.parse(definition, read=DIALECT, error_level=sqlglot.ErrorLevel.RAISE)
    except ParseError:
        return None
    statements = [s for s in parsed if s is not None]
    if len(statements) != 1 or not isinstance(statements[0], exp.Create):
        return None
    select = statements[0].args.get("expression")
    if not isinstance(select, exp.Select):
        return None
    return select.sql(dialect=DIALECT, pretty=True)


@dataclass(frozen=True)
class ViewRef:
    schema_name: str
    view_name: str
    select_body: Optional[str] = None

    @property
    def qualified_name(self) -> str:
        return f"{self.schema_name}.{self.view_name}"


def list_views(
    *,
    server: str,
    database: str,
    user: str,
    password: str,
    driver: str = DEFAULT_ODBC_DRIVER,
    trust_server_certificate: bool = True,
    timeout_s: float = 60.0,
    connect_fn: Optional[ConnectFn] = None,
) -> list[ViewRef]:
    if connect_fn is None:
        connect_fn = connect

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
            cursor.execute(_LIST_VIEWS_SQL)
            views: list[ViewRef] = []
            row = cursor.fetchone()
            while row is not None:
                views.append(
                    ViewRef(
                        schema_name=row[0],
                        view_name=row[1],
                        select_body=_extract_select_body(row[2]),
                    )
                )
                row = cursor.fetchone()
        except pyodbc.Error as exc:
            raise DBCaptureError(f"Failed to list views: {exc}") from exc
    finally:
        connection.close()
    return views
