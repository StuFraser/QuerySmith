import json
import urllib.error
import urllib.request

import pytest

from querysmith.narration.ollama_client import OllamaClientError, generate_json


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_module_contract():
    import querysmith.narration.ollama_client as module

    assert module.__all__ == ["generate_json", "OllamaClientError"]


def test_happy_path_decodes_inner_dict(monkeypatch):
    envelope = json.dumps({"response": json.dumps({"overview": "ok", "findings": []})}).encode("utf-8")

    def fake_urlopen(request, timeout):
        return _FakeResponse(envelope)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = generate_json("prompt", "llama3.1:8b")
    assert result == {"overview": "ok", "findings": []}


def test_connection_refused_raises_client_error(monkeypatch):
    def fake_urlopen(request, timeout):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OllamaClientError):
        generate_json("prompt", "llama3.1:8b")


def test_timeout_raises_client_error(monkeypatch):
    def fake_urlopen(request, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OllamaClientError):
        generate_json("prompt", "llama3.1:8b")


def test_http_error_raises_client_error_naming_status(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(url="http://x", code=500, msg="Internal Error", hdrs=None, fp=None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OllamaClientError, match="500"):
        generate_json("prompt", "llama3.1:8b")


def test_bad_envelope_json_raises_client_error(monkeypatch):
    def fake_urlopen(request, timeout):
        return _FakeResponse(b"not json")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OllamaClientError):
        generate_json("prompt", "llama3.1:8b")


def test_missing_response_field_raises_client_error(monkeypatch):
    def fake_urlopen(request, timeout):
        return _FakeResponse(json.dumps({"not_response": "x"}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OllamaClientError):
        generate_json("prompt", "llama3.1:8b")


def test_inner_response_not_json_raises_client_error(monkeypatch):
    def fake_urlopen(request, timeout):
        return _FakeResponse(json.dumps({"response": "not json"}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(OllamaClientError):
        generate_json("prompt", "llama3.1:8b")


def test_outgoing_request_body_and_url(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeResponse(json.dumps({"response": json.dumps({"overview": "ok", "findings": []})}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    generate_json("hello", "qwen2.5", base_url="http://example:1234", timeout_s=5.0)

    request = captured["request"]
    assert request.full_url == "http://example:1234/api/generate"
    assert request.get_method() == "POST"
    body = json.loads(request.data)
    assert body == {"model": "qwen2.5", "prompt": "hello", "format": "json", "stream": False}
    assert captured["timeout"] == 5.0
