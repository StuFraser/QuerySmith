from querysmith.db.connection import DBCaptureError
from querysmith.web.app import get_connect_fn


class _FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


_BODY = {
    "server": "s",
    "database": "d",
    "user": "u",
    "password": "hunter2",
    "driver": "ODBC Driver 18 for SQL Server",
    "trust_server_certificate": True,
    "timeout_s": 60.0,
}


def test_connect_happy_path_stores_session_and_omits_password(app, client):
    fake_connection = _FakeConnection()

    def fake_connect_fn(**kwargs):
        return fake_connection

    app.dependency_overrides[get_connect_fn] = lambda: fake_connect_fn

    response = client.post("/api/connection", json=_BODY)
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["database"] == "d"
    assert "password" not in body
    assert fake_connection.closed is True


def test_connect_db_capture_error_returns_400(app, client):
    def fake_connect_fn(**kwargs):
        raise DBCaptureError("bad credentials")

    app.dependency_overrides[get_connect_fn] = lambda: fake_connect_fn

    response = client.post("/api/connection", json=_BODY)
    assert response.status_code == 400
    assert "bad credentials" in response.json()["detail"]


def test_get_connection_before_and_after_connect(app, client):
    response = client.get("/api/connection")
    assert response.json() == {
        "connected": False,
        "server": None,
        "database": None,
        "user": None,
        "driver": None,
        "trust_server_certificate": None,
    }

    app.dependency_overrides[get_connect_fn] = lambda: (lambda **kwargs: _FakeConnection())
    client.post("/api/connection", json=_BODY)

    response = client.get("/api/connection")
    body = response.json()
    assert body["connected"] is True
    assert body["server"] == "s"


def test_delete_connection_clears_session_and_views_then_returns_409(app, client):
    app.dependency_overrides[get_connect_fn] = lambda: (lambda **kwargs: _FakeConnection())
    client.post("/api/connection", json=_BODY)

    response = client.delete("/api/connection")
    assert response.status_code == 204

    response = client.get("/api/views")
    assert response.status_code == 409


def test_module_contract():
    import querysmith.web.app as module

    assert set(module.__all__) == {"create_app"}
