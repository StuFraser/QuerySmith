import pyodbc
import pytest

from querysmith.db.connection import DBCaptureError, build_connection_string, connect


def test_connection_string_basic_shape():
    conn_str = build_connection_string(
        server="192.168.1.84,1433",
        database="AdventureWorks2025",
        user="sa",
        password="hunter2",
        trust_server_certificate=True,
    )
    assert "DRIVER={ODBC Driver 18 for SQL Server}" in conn_str
    assert "SERVER=192.168.1.84,1433" in conn_str
    assert "DATABASE=AdventureWorks2025" in conn_str
    assert "UID={sa}" in conn_str
    assert "PWD={hunter2}" in conn_str
    assert "TrustServerCertificate=yes" in conn_str


def test_connection_string_trust_toggle():
    conn_str = build_connection_string(server="s", database="d", user="u", password="p", trust_server_certificate=False)
    assert "TrustServerCertificate=no" in conn_str


def test_password_with_semicolon_is_brace_escaped():
    conn_str = build_connection_string(server="s", database="d", user="u", password="pa;ss")
    assert "PWD={pa;ss}" in conn_str


def test_password_with_literal_brace_is_doubled():
    conn_str = build_connection_string(server="s", database="d", user="u", password="pa}ss")
    assert "PWD={pa}}ss}" in conn_str


def test_pyodbc_error_wrapped_into_db_capture_error(monkeypatch):
    def fake_connect(conn_str, timeout):
        raise pyodbc.OperationalError("08001", "connection refused")

    monkeypatch.setattr(pyodbc, "connect", fake_connect)
    with pytest.raises(DBCaptureError) as exc_info:
        connect(server="s", database="d", user="u", password="p")
    assert exc_info.value.__cause__ is not None


def test_connection_timeout_set_after_connect(monkeypatch):
    class FakeConn:
        timeout = None

    fake_conn = FakeConn()

    def fake_connect(conn_str, timeout):
        return fake_conn

    monkeypatch.setattr(pyodbc, "connect", fake_connect)
    result = connect(server="s", database="d", user="u", password="p", timeout_s=42.0)
    assert result.timeout == 42


def test_module_contract():
    import querysmith.db.connection as module

    assert set(module.__all__) == {"build_connection_string", "connect", "DBCaptureError", "DEFAULT_ODBC_DRIVER"}
