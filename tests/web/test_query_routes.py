import pathlib

from querysmith.db.connection import DBCaptureError
from querysmith.narration import OllamaClientError
from querysmith.web.app import get_capture_fn, get_connect_fn, get_generate_fn

FIXTURES_DIR = pathlib.Path(__file__).parent.parent / "fixtures" / "sqlserver"


class _FakeConnection:
    def close(self):
        pass


_CONNECTION_BODY = {
    "server": "s",
    "database": "d",
    "user": "u",
    "password": "hunter2",
    "driver": "ODBC Driver 18 for SQL Server",
    "trust_server_certificate": True,
    "timeout_s": 60.0,
}


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def _connect(app, client):
    app.dependency_overrides[get_connect_fn] = lambda: (lambda **kwargs: _FakeConnection())
    client.post("/api/connection", json=_CONNECTION_BODY)


def test_query_without_connection_returns_409(client):
    response = client.post("/api/query", json={"query": "SELECT 1"})
    assert response.status_code == 409


def test_query_invalid_shape_returns_422_without_connecting(app, client):
    _connect(app, client)
    # get_capture_fn is left un-overridden -- the real capture_plan_xml runs,
    # and validate_select_only rejects this before any DB connection is
    # attempted (mirrors tests/db/test_capture.py's equivalent case).
    response = client.post("/api/query", json={"query": "SELECT 1; DROP TABLE x"})
    assert response.status_code == 422
    assert "stacked" in response.json()["detail"].lower() or "statement" in response.json()["detail"].lower()


def test_query_db_capture_error_returns_502(app, client):
    _connect(app, client)

    def fake_capture_fn(**kwargs):
        raise DBCaptureError("query execution failed")

    app.dependency_overrides[get_capture_fn] = lambda: fake_capture_fn

    response = client.post("/api/query", json={"query": "SELECT 1"})
    assert response.status_code == 502
    assert "query execution failed" in response.json()["detail"]


def test_query_happy_path_with_model_narration(app, client):
    _connect(app, client)
    xml = _load_fixture("simple_index_seek.xml")

    app.dependency_overrides[get_capture_fn] = lambda: (lambda **kwargs: xml)
    app.dependency_overrides[get_generate_fn] = lambda: (
        lambda prompt, model, **kwargs: {"overview": "All good", "findings": []}
    )

    response = client.post("/api/query", json={"query": "SELECT * FROM dbo.Customers WHERE CustomerID = 4471"})
    assert response.status_code == 200
    body = response.json()
    assert body["narration"]["overview"] == "All good"
    assert body["narration"]["overview_source"] == "model"
    assert body["narration"]["degraded"] is False
    assert "summary" in body
    assert isinstance(body["findings"], list)


def test_query_narration_degrades_gracefully_when_model_unreachable(app, client):
    _connect(app, client)
    xml = _load_fixture("simple_index_seek.xml")

    def failing_generate_fn(prompt, model, **kwargs):
        raise OllamaClientError("connection refused")

    app.dependency_overrides[get_capture_fn] = lambda: (lambda **kwargs: xml)
    app.dependency_overrides[get_generate_fn] = lambda: failing_generate_fn

    response = client.post("/api/query", json={"query": "SELECT * FROM dbo.Customers WHERE CustomerID = 4471"})
    assert response.status_code == 200
    body = response.json()
    assert body["narration"]["degraded"] is True
    assert "client_error" in body["narration"]["degraded_reason"]


def test_query_narrate_false_skips_narration(app, client):
    _connect(app, client)
    xml = _load_fixture("simple_index_seek.xml")
    calls = []

    app.dependency_overrides[get_capture_fn] = lambda: (lambda **kwargs: xml)
    app.dependency_overrides[get_generate_fn] = lambda: (
        lambda prompt, model, **kwargs: calls.append(1) or {"overview": "x", "findings": []}
    )

    response = client.post("/api/query", json={"query": "SELECT 1", "narrate": False})
    assert response.status_code == 200
    assert response.json()["narration"] is None
    assert calls == []


def test_query_redact_is_currently_a_stub_noop(app, client):
    # See design-notes/execution-plan-web-ui.md: parse_plan_xml's `redact`
    # is an identity-passthrough stub today. This test documents that known
    # behavior rather than silently asserting the wrong thing -- once real
    # literal redaction lands, this assertion should flip.
    _connect(app, client)
    xml = _load_fixture("simple_index_seek.xml")

    app.dependency_overrides[get_capture_fn] = lambda: (lambda **kwargs: xml)
    app.dependency_overrides[get_generate_fn] = lambda: (
        lambda prompt, model, **kwargs: {"overview": "x", "findings": []}
    )

    response = client.post(
        "/api/query", json={"query": "SELECT * FROM dbo.Customers WHERE CustomerID = 4471", "redact": True}
    )
    assert response.status_code == 200
    assert "4471" in response.json()["summary"]["statement_text"]
