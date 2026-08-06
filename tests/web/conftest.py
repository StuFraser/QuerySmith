import pytest
from fastapi.testclient import TestClient

from querysmith.web.app import create_app
from querysmith.web.last_result import LastResultStore, get_last_result_store
from querysmith.web.session import SessionStore, get_session_store


@pytest.fixture
def app():
    # Each test gets its own SessionStore/LastResultStore override -- the
    # module-level singletons in session.py/last_result.py are intentionally
    # process-wide for real usage, but tests must not leak state across tests.
    app = create_app()
    store = SessionStore()
    app.dependency_overrides[get_session_store] = lambda: store
    last_result_store = LastResultStore()
    app.dependency_overrides[get_last_result_store] = lambda: last_result_store
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    return TestClient(app)
