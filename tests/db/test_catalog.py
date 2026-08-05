import pyodbc
import pytest

from querysmith.db.catalog import list_views, ViewRef
from querysmith.db.connection import DBCaptureError


def _connect_fn_factory(connection):
    calls = []

    def connect_fn(**kwargs):
        calls.append(kwargs)
        return connection

    connect_fn.calls = calls
    return connect_fn


def test_happy_path_returns_ordered_views(fake_cursor_factory, fake_connection_factory):
    result_sets = [
        (
            [("schema_name",), ("view_name",)],
            [("dbo", "Orders"), ("sales", "MonthlyTotals")],
        ),
    ]
    cursor = fake_cursor_factory(result_sets)
    connection = fake_connection_factory(cursor)
    connect_fn = _connect_fn_factory(connection)

    views = list_views(server="s", database="d", user="u", password="p", connect_fn=connect_fn)

    assert views == [
        ViewRef(schema_name="dbo", view_name="Orders"),
        ViewRef(schema_name="sales", view_name="MonthlyTotals"),
    ]
    assert views[0].qualified_name == "dbo.Orders"
    assert cursor.executed_statements == [
        "SELECT s.name AS schema_name, v.name AS view_name "
        "FROM sys.views v JOIN sys.schemas s ON v.schema_id = s.schema_id "
        "ORDER BY s.name, v.name;"
    ]
    assert connection.closed is True


def test_empty_result_returns_empty_list(fake_cursor_factory, fake_connection_factory):
    cursor = fake_cursor_factory([([("schema_name",), ("view_name",)], [])])
    connection = fake_connection_factory(cursor)
    connect_fn = _connect_fn_factory(connection)

    views = list_views(server="s", database="d", user="u", password="p", connect_fn=connect_fn)

    assert views == []
    assert connection.closed is True


def test_execute_error_wrapped_and_connection_closed(fake_cursor_factory, fake_connection_factory):
    cursor = fake_cursor_factory([])
    cursor.raise_on_execute = pyodbc.ProgrammingError("42000", "permission denied")
    connection = fake_connection_factory(cursor)
    connect_fn = _connect_fn_factory(connection)

    with pytest.raises(DBCaptureError):
        list_views(server="s", database="d", user="u", password="p", connect_fn=connect_fn)
    assert connection.closed is True


def test_module_contract():
    import querysmith.db.catalog as module

    assert set(module.__all__) == {"list_views", "ViewRef"}
