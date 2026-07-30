import pyodbc
import pytest

from querysmith.db.capture import capture_plan_xml
from querysmith.db.connection import DBCaptureError
from querysmith.db.query_safety import QueryValidationError


def _connect_fn_factory(connection):
    calls = []

    def connect_fn(**kwargs):
        calls.append(kwargs)
        return connection

    connect_fn.calls = calls
    return connect_fn


def test_happy_path_finds_showplan_xml(fake_cursor_factory, fake_connection_factory):
    plan_xml = "<ShowPlanXML>...</ShowPlanXML>"
    result_sets = [
        (None, []),  # SET STATISTICS XML ON produces no result set
        ([("col1",)], [("data",)]),  # the SELECT's own data
        ([("Microsoft SQL Server 2005 XML Showplan",)], [(plan_xml,)]),  # the plan
        (None, []),  # SET STATISTICS XML OFF
    ]
    cursor = fake_cursor_factory(result_sets)
    connection = fake_connection_factory(cursor)
    connect_fn = _connect_fn_factory(connection)

    xml = capture_plan_xml(
        server="s",
        database="d",
        user="u",
        password="p",
        query="SELECT * FROM dbo.QuerySmith_test1",
        connect_fn=connect_fn,
    )
    assert xml == plan_xml
    assert cursor.executed_statements == [
        "SET STATISTICS XML ON; SELECT * FROM dbo.QuerySmith_test1; SET STATISTICS XML OFF;"
    ]
    assert connection.closed is True


def test_invalid_query_rejected_before_connecting(fake_connection_factory, fake_cursor_factory):
    connection = fake_connection_factory(fake_cursor_factory([]))
    connect_fn = _connect_fn_factory(connection)

    with pytest.raises(QueryValidationError):
        capture_plan_xml(
            server="s",
            database="d",
            user="u",
            password="p",
            query="SELECT 1; DROP TABLE x",
            connect_fn=connect_fn,
        )
    assert connect_fn.calls == []


def test_no_showplan_xml_found_raises_db_capture_error(fake_cursor_factory, fake_connection_factory):
    result_sets = [(None, []), ([("col1",)], [("data",)]), (None, [])]
    cursor = fake_cursor_factory(result_sets)
    connection = fake_connection_factory(cursor)
    connect_fn = _connect_fn_factory(connection)

    with pytest.raises(DBCaptureError):
        capture_plan_xml(
            server="s",
            database="d",
            user="u",
            password="p",
            query="SELECT * FROM dbo.QuerySmith_test1",
            connect_fn=connect_fn,
        )
    assert connection.closed is True


def test_execute_error_wrapped_and_connection_closed(fake_cursor_factory, fake_connection_factory):
    cursor = fake_cursor_factory([])
    cursor.raise_on_execute = pyodbc.ProgrammingError("42000", "invalid object name")
    connection = fake_connection_factory(cursor)
    connect_fn = _connect_fn_factory(connection)

    with pytest.raises(DBCaptureError):
        capture_plan_xml(
            server="s",
            database="d",
            user="u",
            password="p",
            query="SELECT * FROM dbo.NoSuchThing",
            connect_fn=connect_fn,
        )
    assert connection.closed is True


def test_query_without_trailing_semicolon_gets_one_added(fake_cursor_factory, fake_connection_factory):
    plan_xml = "<ShowPlanXML>...</ShowPlanXML>"
    result_sets = [([("x",)], [(plan_xml,)])]
    cursor = fake_cursor_factory(result_sets)
    connection = fake_connection_factory(cursor)
    connect_fn = _connect_fn_factory(connection)

    capture_plan_xml(
        server="s",
        database="d",
        user="u",
        password="p",
        query="SELECT 1",
        connect_fn=connect_fn,
    )
    assert cursor.executed_statements[0] == "SET STATISTICS XML ON; SELECT 1; SET STATISTICS XML OFF;"


def test_module_contract():
    import querysmith.db.capture as module

    assert module.__all__ == ["capture_plan_xml"]
