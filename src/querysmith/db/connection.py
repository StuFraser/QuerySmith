"""pyodbc connection construction for live SQL Server capture (see
design-notes/execution-plan-agent-scope.md). Connection string is built
entirely from structured parameters -- it never touches user-supplied query
text (that's capture.py's job, gated through query_safety first). Single
error type wraps every pyodbc.Error so callers never see a raw driver
exception (mirrors OllamaClientError in narration/ollama_client.py).
"""

from __future__ import annotations

import pyodbc

__all__ = ["build_connection_string", "connect", "DBCaptureError", "DEFAULT_ODBC_DRIVER"]

DEFAULT_ODBC_DRIVER = "ODBC Driver 18 for SQL Server"


class DBCaptureError(Exception):
    """Connection failed, authentication failed, query execution failed, or
    the result shape wasn't what capture expected. Callers catch this single
    type rather than pyodbc.Error/pyodbc.OperationalError/etc individually."""


def _odbc_escape(value: str) -> str:
    # ODBC connection-string values containing ';', '=', '{', '}' must be
    # brace-wrapped, with any literal '}' doubled -- otherwise a password
    # containing ';' silently truncates/corrupts the connection string.
    return "{" + value.replace("}", "}}") + "}"


def build_connection_string(
    *,
    server: str,
    database: str,
    user: str,
    password: str,
    driver: str = DEFAULT_ODBC_DRIVER,
    trust_server_certificate: bool = True,
) -> str:
    trust = "yes" if trust_server_certificate else "no"
    return (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
        f"UID={_odbc_escape(user)};PWD={_odbc_escape(password)};"
        f"TrustServerCertificate={trust};"
    )


def connect(
    *,
    server: str,
    database: str,
    user: str,
    password: str,
    driver: str = DEFAULT_ODBC_DRIVER,
    trust_server_certificate: bool = True,
    timeout_s: float = 60.0,
) -> pyodbc.Connection:
    conn_str = build_connection_string(
        server=server,
        database=database,
        user=user,
        password=password,
        driver=driver,
        trust_server_certificate=trust_server_certificate,
    )
    # pyodbc's timeout params map to a whole-seconds ODBC/DBAPI value and
    # reject a float (TypeError), so timeout_s is rounded to int here --
    # callers still pass a float for symmetry with the Ollama timeout knob.
    timeout_whole_s = int(round(timeout_s))
    try:
        connection = pyodbc.connect(conn_str, timeout=timeout_whole_s)
    except pyodbc.Error as exc:
        raise DBCaptureError(f"Failed to connect to SQL Server: {exc}") from exc
    connection.timeout = timeout_whole_s  # query execution timeout (SQL_ATTR_QUERY_TIMEOUT)
    return connection
