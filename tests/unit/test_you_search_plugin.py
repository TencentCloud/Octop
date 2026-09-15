"""You-search plugin: endpoint selection, auth header, result parsing."""

from __future__ import annotations

import importlib.util
from typing import Any

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root


def _load_you_search():
    path = default_bundled_plugins_root() / "you-search" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_you_search", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeResp:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status
        self.headers = {"content-type": "application/json"}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> Any:
        return self._payload


class _RecordingClient:
    last_url = ""
    last_headers: dict[str, str] = {}
    last_json: Any = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> _RecordingClient:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def post(self, url: str, **kwargs: Any) -> _FakeResp:
        type(self).last_url = url
        type(self).last_headers = dict(kwargs.get("headers") or {})
        type(self).last_json = kwargs.get("json")
        text = (
            '{"results":{"web":['
            '{"url":"https://example.com/a","title":"First","page_age":"2026-01-02T03:04:05"},'
            '{"url":"https://example.com/b","title":"Second"}'
            "]}}"
        )
        return _FakeResp(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [{"type": "text", "text": text}],
                },
            },
        )


def test_keyless_endpoint_used_without_api_key(monkeypatch) -> None:
    mod = _load_you_search()
    monkeypatch.delenv("YDC_API_KEY", raising=False)
    monkeypatch.setattr(mod.httpx, "Client", _RecordingClient)
    items = mod._search("rust release", 5)
    assert mod._ENDPOINT_KEYLESS in _RecordingClient.last_url
    assert "Authorization" not in _RecordingClient.last_headers
    assert len(items) == 2
    assert items[0]["title"] == "First"
    assert items[0]["url"] == "https://example.com/a"
    assert items[0]["extra"] == "2026-01-02"
    assert items[1]["rank"] == 2


def test_authed_endpoint_and_bearer_header_with_env_key(monkeypatch) -> None:
    mod = _load_you_search()
    monkeypatch.setenv("YDC_API_KEY", "test-key-123")
    monkeypatch.setattr(mod.httpx, "Client", _RecordingClient)
    mod._search("rust release", 5)
    assert _RecordingClient.last_url == mod._ENDPOINT_AUTHED
    assert _RecordingClient.last_headers.get("Authorization") == "Bearer test-key-123"
    body = _RecordingClient.last_json
    assert body["method"] == "tools/call"
    assert body["params"]["name"] == "you-search"
    assert body["params"]["arguments"]["query"] == "rust release"


class _SseResp:
    """``text/event-stream`` response: result arrives on a ``data:`` line."""

    status_code = 200

    def __init__(self, text: str) -> None:
        self.text = text
        self.headers = {"content-type": "text/event-stream"}

    def raise_for_status(self) -> None:
        return None


def test_sse_framed_response_is_parsed() -> None:
    mod = _load_you_search()
    result_text = '{"results":{"web":[{"url":"https://example.com/sse","title":"SSE item"}]}}'
    import json as _json

    body = _json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": result_text}]},
        },
    )
    resp = _SseResp(f"event: message\ndata: {body}\n")
    payload = mod._rpc_payload(resp)
    items = mod._parse_web_results(_json.loads(mod._result_text(payload["result"]["content"])))
    assert len(items) == 1
    assert items[0]["title"] == "SSE item"


def test_empty_query_returns_error_payload() -> None:
    import asyncio
    import json as _json

    mod = _load_you_search()
    out = asyncio.run(mod.you_search("   "))
    d = _json.loads(out)
    assert d["data"]["error"] == "empty query"
