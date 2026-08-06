import pathlib

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


def _run_query_without_narration(app, client, fixture="large_table_scan.xml"):
    xml = _load_fixture(fixture)
    app.dependency_overrides[get_capture_fn] = lambda: (lambda **kwargs: xml)
    response = client.post("/api/query", json={"query": "SELECT * FROM dbo.BigTable", "narrate": False})
    assert response.status_code == 200
    return response.json()


def test_propose_fix_without_prior_query_returns_409(app, client):
    _connect(app, client)
    response = client.post("/api/propose-fix", json={})
    assert response.status_code == 409


def test_propose_fix_without_connection_or_query_returns_409(client):
    response = client.post("/api/propose-fix", json={})
    assert response.status_code == 409


def test_propose_fix_happy_path(app, client):
    _connect(app, client)
    body = _run_query_without_narration(app, client)
    scan_index = next(i for i, f in enumerate(body["findings"]) if f["rule_id"] == "large_table_scan")

    def fake_generate_fn(prompt, model, **kwargs):
        return {
            "fixes": [
                {
                    "finding_index": scan_index,
                    "rewritten_query": "SELECT Id FROM dbo.BigTable WHERE Status = 1",
                    "index_script": "CREATE INDEX IX_BigTable_Status ON dbo.BigTable (Status);",
                }
            ]
        }

    app.dependency_overrides[get_generate_fn] = lambda: fake_generate_fn
    response = client.post("/api/propose-fix", json={})
    assert response.status_code == 200
    result = response.json()
    assert result["degraded"] is False
    assert result["fixes"] == [
        {
            "finding_index": scan_index,
            "rewritten_query": "SELECT Id FROM dbo.BigTable WHERE Status = 1",
            "index_script": "CREATE INDEX IX_BigTable_Status ON dbo.BigTable (Status);",
        }
    ]


def test_propose_fix_reuses_cached_result_without_capture_fn_override(app, client):
    # After the initial /api/query call, /api/propose-fix must not need
    # get_capture_fn at all -- it only reads the cached findings/summary.
    _connect(app, client)
    body = _run_query_without_narration(app, client)
    scan_index = next(i for i, f in enumerate(body["findings"]) if f["rule_id"] == "large_table_scan")
    app.dependency_overrides.pop(get_capture_fn, None)

    app.dependency_overrides[get_generate_fn] = lambda: (
        lambda prompt, model, **kwargs: {"fixes": [{"finding_index": scan_index, "rewritten_query": "SELECT 1"}]}
    )
    response = client.post("/api/propose-fix", json={})
    assert response.status_code == 200


def test_propose_fix_degraded_when_model_unreachable(app, client):
    _connect(app, client)
    _run_query_without_narration(app, client)

    def failing_generate_fn(prompt, model, **kwargs):
        raise OllamaClientError("connection refused")

    app.dependency_overrides[get_generate_fn] = lambda: failing_generate_fn
    response = client.post("/api/propose-fix", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["degraded"] is True
    assert "client_error" in body["degraded_reason"]
    assert body["fixes"] == []


def test_propose_fix_after_disconnect_returns_409(app, client):
    _connect(app, client)
    _run_query_without_narration(app, client)
    client.delete("/api/connection")
    response = client.post("/api/propose-fix", json={})
    assert response.status_code == 409
