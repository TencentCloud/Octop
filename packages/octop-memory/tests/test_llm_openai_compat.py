"""Tests for the production ``OpenAICompatClient``.

All network I/O is faked by monkeypatching ``request.urlopen`` in the
client module — no sockets are opened.
"""

from __future__ import annotations

import io
import json
from typing import Any
from urllib import error

import pytest

from octop_memory.ports.llm._protocol import LLMClientError
from octop_memory.ports.llm.openai_compat import OpenAICompatClient


def _ok_response(content: str = "hello") -> io.BytesIO:
    body = json.dumps({"choices": [{"message": {"role": "assistant", "content": content}}]}).encode()

    class _Resp(io.BytesIO):
        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *args: object) -> None:
            self.close()

    return _Resp(body)


class _FakeUrlopen:
    """Replays a scripted sequence of responses / exceptions."""

    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = list(outcomes)
        self.requests: list[Any] = []

    def __call__(self, req: Any, timeout: float | None = None) -> Any:
        self.requests.append(req)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _client(**kwargs: Any) -> OpenAICompatClient:
    defaults: dict[str, Any] = {
        "base_url": "https://api.example.com/v1",
        "model": "small",
        "api_key": "k",
        "retry_backoff_seconds": 0,
    }
    defaults.update(kwargs)
    return OpenAICompatClient(**defaults)


def _request_body(req: Any) -> dict[str, Any]:
    return json.loads(req.data.decode("utf-8"))


class TestTierMapping:
    def test_light_and_heavy_map_to_distinct_models(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeUrlopen([_ok_response(), _ok_response()])
        monkeypatch.setattr("octop_memory.ports.llm.openai_compat.request.urlopen", fake)
        client = _client(model_heavy="big")

        client.call_llm("p", tier="light")
        client.call_llm("p", tier="heavy")

        assert _request_body(fake.requests[0])["model"] == "small"
        assert _request_body(fake.requests[1])["model"] == "big"

    def test_heavy_defaults_to_light_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeUrlopen([_ok_response()])
        monkeypatch.setattr("octop_memory.ports.llm.openai_compat.request.urlopen", fake)

        _client().call_llm("p", tier="heavy")

        assert _request_body(fake.requests[0])["model"] == "small"


class TestAuth:
    def test_api_key_sets_bearer_header(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeUrlopen([_ok_response()])
        monkeypatch.setattr("octop_memory.ports.llm.openai_compat.request.urlopen", fake)

        _client(api_key="sk-test").call_llm("p")

        assert fake.requests[0].get_header("Authorization") == "Bearer sk-test"

    def test_missing_key_omits_header(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OCTOPMEMORY_LLM_API_KEY", raising=False)
        fake = _FakeUrlopen([_ok_response()])
        monkeypatch.setattr("octop_memory.ports.llm.openai_compat.request.urlopen", fake)

        OpenAICompatClient(base_url="http://localhost:8000/v1", model="m", retry_backoff_seconds=0).call_llm("p")

        assert fake.requests[0].get_header("Authorization") is None

    def test_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MY_KEY_VAR", "sk-env")
        fake = _FakeUrlopen([_ok_response()])
        monkeypatch.setattr("octop_memory.ports.llm.openai_compat.request.urlopen", fake)

        OpenAICompatClient(
            base_url="https://api.example.com/v1",
            model="m",
            api_key_env="MY_KEY_VAR",
            retry_backoff_seconds=0,
        ).call_llm("p")

        assert fake.requests[0].get_header("Authorization") == "Bearer sk-env"


class TestRetries:
    def _http_error(self, code: int) -> error.HTTPError:
        return error.HTTPError("https://api.example.com/v1/chat/completions", code, "boom", {}, io.BytesIO(b""))

    def test_retries_transient_500_then_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeUrlopen([self._http_error(500), _ok_response("recovered")])
        monkeypatch.setattr("octop_memory.ports.llm.openai_compat.request.urlopen", fake)

        assert _client().call_llm("p") == "recovered"
        assert len(fake.requests) == 2

    def test_does_not_retry_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeUrlopen([self._http_error(400), _ok_response()])
        monkeypatch.setattr("octop_memory.ports.llm.openai_compat.request.urlopen", fake)

        with pytest.raises(LLMClientError):
            _client().call_llm("p")
        assert len(fake.requests) == 1

    def test_exhausted_retries_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeUrlopen([self._http_error(503)] * 3)
        monkeypatch.setattr("octop_memory.ports.llm.openai_compat.request.urlopen", fake)

        with pytest.raises(LLMClientError):
            _client(max_retries=2).call_llm("p")
        assert len(fake.requests) == 3

    def test_retries_network_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeUrlopen([error.URLError("conn refused"), _ok_response("ok")])
        monkeypatch.setattr("octop_memory.ports.llm.openai_compat.request.urlopen", fake)

        assert _client().call_llm("p") == "ok"


class TestRequestShape:
    def test_json_response_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeUrlopen([_ok_response()])
        monkeypatch.setattr("octop_memory.ports.llm.openai_compat.request.urlopen", fake)

        _client().call_llm("p", response_format="json", temperature=0.0, system="sys")

        body = _request_body(fake.requests[0])
        assert body["response_format"] == {"type": "json_object"}
        assert body["temperature"] == 0.0
        assert body["messages"][0] == {"role": "system", "content": "sys"}

    def test_bad_payload_shape_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Resp(io.BytesIO):
            def __enter__(self) -> _Resp:
                return self

            def __exit__(self, *args: object) -> None:
                self.close()

        fake = _FakeUrlopen([_Resp(b'{"unexpected": true}')])
        monkeypatch.setattr("octop_memory.ports.llm.openai_compat.request.urlopen", fake)

        with pytest.raises(LLMClientError):
            _client().call_llm("p")


class TestFromConfig:
    def test_builds_from_bridge_llm_block(self) -> None:
        client = OpenAICompatClient.from_config(
            {
                "endpoint": "https://api.deepseek.com/v1",
                "model": "deepseek-chat",
                "model_heavy": "deepseek-reasoner",
                "api_key": "sk-x",
                "timeout_seconds": 30,
            }
        )
        assert client._models == {"light": "deepseek-chat", "heavy": "deepseek-reasoner"}

    def test_missing_endpoint_raises(self) -> None:
        with pytest.raises(LLMClientError):
            OpenAICompatClient.from_config({"model": "m"})

    def test_missing_model_raises(self) -> None:
        with pytest.raises(LLMClientError):
            OpenAICompatClient.from_config({"endpoint": "https://x/v1"})
