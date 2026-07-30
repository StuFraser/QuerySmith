import argparse
import pathlib

from querysmith.cli import EXIT_CAPTURE_ERROR, EXIT_OK, EXIT_USAGE_ERROR, PASSWORD_ENV_VAR, run
from querysmith.db import DBCaptureError, QueryValidationError

FIXTURES_DIR = pathlib.Path(__file__).parent.parent / "fixtures" / "sqlserver"

_BASE_ARGS = dict(
    server="s",
    database="d",
    user="readonly_login",
    query="SELECT 1",
    driver="ODBC Driver 18 for SQL Server",
    trust_server_certificate=True,
    timeout=60.0,
    narrate=True,
    model="llama3.2:3b",
    ollama_timeout=600.0,
)


def _args(**overrides):
    values = dict(_BASE_ARGS)
    values.update(overrides)
    return argparse.Namespace(**values)


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_missing_password_env_var(monkeypatch, capsys):
    monkeypatch.delenv(PASSWORD_ENV_VAR, raising=False)
    calls = []

    def capture_fn(**kwargs):
        calls.append(kwargs)
        return "<ignored/>"

    exit_code = run(_args(), capture_fn=capture_fn)
    assert exit_code == EXIT_USAGE_ERROR
    assert calls == []
    assert PASSWORD_ENV_VAR in capsys.readouterr().err


def test_happy_path(monkeypatch, capsys):
    monkeypatch.setenv(PASSWORD_ENV_VAR, "hunter2")
    xml = _load_fixture("simple_index_seek.xml")

    def capture_fn(**kwargs):
        return xml

    def narration_client(prompt, model):
        return {"overview": "All good", "findings": []}

    exit_code = run(_args(), capture_fn=capture_fn, narration_client=narration_client)
    assert exit_code == EXIT_OK
    out = capsys.readouterr().out
    assert "QuerySmith Execution Plan Report" in out
    assert "All good" in out


def test_query_validation_error(monkeypatch, capsys):
    monkeypatch.setenv(PASSWORD_ENV_VAR, "hunter2")

    def capture_fn(**kwargs):
        raise QueryValidationError("bad query")

    exit_code = run(_args(), capture_fn=capture_fn)
    assert exit_code == EXIT_USAGE_ERROR
    assert "bad query" in capsys.readouterr().err


def test_db_capture_error(monkeypatch, capsys):
    monkeypatch.setenv(PASSWORD_ENV_VAR, "hunter2")

    def capture_fn(**kwargs):
        raise DBCaptureError("connection refused")

    exit_code = run(_args(), capture_fn=capture_fn)
    assert exit_code == EXIT_CAPTURE_ERROR
    assert "connection refused" in capsys.readouterr().err


def test_no_narrate_skips_narration_client(monkeypatch, capsys):
    monkeypatch.setenv(PASSWORD_ENV_VAR, "hunter2")
    xml = _load_fixture("simple_index_seek.xml")
    calls = []

    def capture_fn(**kwargs):
        return xml

    def narration_client(prompt, model):
        calls.append((prompt, model))
        return {"overview": "x", "findings": []}

    exit_code = run(_args(narrate=False), capture_fn=capture_fn, narration_client=narration_client)
    assert exit_code == EXIT_OK
    assert calls == []
    assert "narration disabled" in capsys.readouterr().out.lower()


def test_privileged_user_prints_reminder(monkeypatch, capsys):
    monkeypatch.setenv(PASSWORD_ENV_VAR, "hunter2")
    xml = _load_fixture("simple_index_seek.xml")

    def capture_fn(**kwargs):
        return xml

    def narration_client(prompt, model):
        return {"overview": "x", "findings": []}

    run(_args(user="sa"), capture_fn=capture_fn, narration_client=narration_client)
    assert "Reminder" in capsys.readouterr().err


def test_non_privileged_user_no_reminder(monkeypatch, capsys):
    monkeypatch.setenv(PASSWORD_ENV_VAR, "hunter2")
    xml = _load_fixture("simple_index_seek.xml")

    def capture_fn(**kwargs):
        return xml

    def narration_client(prompt, model):
        return {"overview": "x", "findings": []}

    run(_args(user="readonly_login"), capture_fn=capture_fn, narration_client=narration_client)
    assert "Reminder" not in capsys.readouterr().err


def test_password_never_appears_in_output(monkeypatch, capsys):
    monkeypatch.setenv(PASSWORD_ENV_VAR, "s3cr3t-p@ss")
    xml = _load_fixture("simple_index_seek.xml")

    def capture_fn(**kwargs):
        assert kwargs["password"] == "s3cr3t-p@ss"
        return xml

    def narration_client(prompt, model):
        return {"overview": "x", "findings": []}

    run(_args(), capture_fn=capture_fn, narration_client=narration_client)
    captured = capsys.readouterr()
    assert "s3cr3t-p@ss" not in captured.out
    assert "s3cr3t-p@ss" not in captured.err


def test_module_contract():
    import querysmith.cli as module

    assert set(module.__all__) == {"main", "run", "format_report"}
