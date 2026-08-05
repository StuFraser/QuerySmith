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

from querysmith.db.connection import DBCaptureError, DEFAULT_ODBC_DRIVER, connect

__all__ = ["list_views", "ViewRef"]

ConnectFn = Callable[..., pyodbc.Connection]

# Fixed, non-user-influenced template -- mirrors capture.py's _STATEMENT_TEMPLATE.
_LIST_VIEWS_SQL = (
    "SELECT s.name AS schema_name, v.name AS view_name "
    "FROM sys.views v JOIN sys.schemas s ON v.schema_id = s.schema_id "
    "ORDER BY s.name, v.name;"
)


@dataclass(frozen=True)
class ViewRef:
    schema_name: str
    view_name: str

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
                views.append(ViewRef(schema_name=row[0], view_name=row[1]))
                row = cursor.fetchone()
        except pyodbc.Error as exc:
            raise DBCaptureError(f"Failed to list views: {exc}") from exc
    finally:
        connection.close()
    return views
