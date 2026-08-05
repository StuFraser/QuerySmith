import pytest
from fastapi.testclient import TestClient

from querysmith.web.app import create_app
from querysmith.web.session import SessionStore, get_session_store


@pytest.fixture
def app():
    # Each test gets its own SessionStore override -- the module-level
    # singleton in session.py is intentionally process-wide for real usage,
    # but tests must not leak connection state into one another.
    app = create_app()
    store = SessionStore()
    app.dependency_overrides[get_session_store] = lambda: store
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    return TestClient(app)
