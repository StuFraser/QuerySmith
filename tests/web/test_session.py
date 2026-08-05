import threading

import pytest

from querysmith.web.session import ConnectionParams, NotConnectedError, SessionStore


def _params(**overrides):
    values = dict(
        server="s",
        database="d",
        user="u",
        password="s3cr3t-p@ss",
        driver="ODBC Driver 18 for SQL Server",
        trust_server_certificate=True,
        timeout_s=60.0,
    )
    values.update(overrides)
    return ConnectionParams(**values)


def test_get_before_set_raises():
    store = SessionStore()
    with pytest.raises(NotConnectedError):
        store.get()
    assert store.is_connected() is False


def test_set_get_clear_roundtrip():
    store = SessionStore()
    params = _params()
    store.set(params)
    assert store.is_connected() is True
    assert store.get() == params
    store.clear()
    assert store.is_connected() is False
    with pytest.raises(NotConnectedError):
        store.get()


def test_repr_never_contains_password():
    params = _params()
    assert "s3cr3t-p@ss" not in repr(params)
    assert "server='s'" in repr(params)


def test_concurrent_set_does_not_raise():
    store = SessionStore()
    errors = []

    def worker(i):
        try:
            store.set(_params(server=f"s{i}"))
        except Exception as exc:  # pragma: no cover - failure path only
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert store.is_connected() is True


def test_module_contract():
    import querysmith.web.session as module

    assert set(module.__all__) == {"ConnectionParams", "SessionStore", "get_session_store", "NotConnectedError"}
