from querysmith.db.catalog import ViewRef
from querysmith.db.connection import DBCaptureError
from querysmith.web.app import get_connect_fn, get_list_views_fn


class _FakeConnection:
    def close(self):
        pass


_BODY = {
    "server": "s",
    "database": "d",
    "user": "u",
    "password": "hunter2",
    "driver": "ODBC Driver 18 for SQL Server",
    "trust_server_certificate": True,
    "timeout_s": 60.0,
}


def _connect(app, client):
    app.dependency_overrides[get_connect_fn] = lambda: (lambda **kwargs: _FakeConnection())
    client.post("/api/connection", json=_BODY)


def test_views_without_connection_returns_409(client):
    response = client.get("/api/views")
    assert response.status_code == 409


def test_views_happy_path(app, client):
    _connect(app, client)

    def fake_list_views_fn(**kwargs):
        return [
            ViewRef(schema_name="dbo", view_name="Orders", select_body="SELECT o.Id\nFROM dbo.T AS o"),
            ViewRef(schema_name="dbo", view_name="Encrypted", select_body=None),
        ]

    app.dependency_overrides[get_list_views_fn] = lambda: fake_list_views_fn

    response = client.get("/api/views")
    assert response.status_code == 200
    assert response.json()["views"] == [
        {
            "schema_name": "dbo",
            "view_name": "Orders",
            "qualified_name": "dbo.Orders",
            "select_body": "SELECT o.Id\nFROM dbo.T AS o",
        },
        {
            "schema_name": "dbo",
            "view_name": "Encrypted",
            "qualified_name": "dbo.Encrypted",
            "select_body": None,
        },
    ]


def test_views_db_capture_error_returns_502(app, client):
    _connect(app, client)

    def fake_list_views_fn(**kwargs):
        raise DBCaptureError("connection dropped")

    app.dependency_overrides[get_list_views_fn] = lambda: fake_list_views_fn

    response = client.get("/api/views")
    assert response.status_code == 502
    assert "connection dropped" in response.json()["detail"]
