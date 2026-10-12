"""Short-link plugin must surface is.gd's own error text instead of a parse failure."""

from __future__ import annotations

import importlib.util
import json
from typing import Any

import pytest

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root


def _load_short_link():  # type: ignore[no-untyped-def]
    path = default_bundled_plugins_root() / "short-link" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_short_link", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Resp:
    def __init__(self, payload: Any = None, text: str = "") -> None:
        self._payload = payload
        self.text = text
        self.status_code = 200

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> Any:
        if self._payload is None:
            raise json.JSONDecodeError("Expecting value", self.text, 0)
        return self._payload


def _client_class(resp: _Resp, calls: list[dict[str, Any]]):  # type: ignore[no-untyped-def]
    class _Client:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def get(self, url: str, **kwargs: Any) -> _Resp:
            calls.append({"url": url, **kwargs})
            return resp

    return _Client


async def _run(monkeypatch: pytest.MonkeyPatch, resp: _Resp) -> tuple[dict[str, Any], Any]:
    mod = _load_short_link()
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(mod.httpx, "Client", _client_class(resp, calls))
    raw = await mod.make_short_link("https://example.com/a")
    envelope = json.loads(raw)
    return {**envelope["data"], "text": envelope["text"]}, calls


async def test_plain_text_error_body_is_reported_to_the_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """is.gd answers a format=json request with text/html when its own insert fails."""
    data, _ = await _run(monkeypatch, _Resp(text="Error, database insert failed"))
    assert data["error"] == "Error, database insert failed"
    assert "Expecting value" not in data["text"]


async def test_json_error_code_keeps_the_upstream_message(monkeypatch: pytest.MonkeyPatch) -> None:
    data, _ = await _run(
        monkeypatch, _Resp(payload={"errorcode": 1, "errormessage": "Duplicate short code."})
    )
    assert data["error"] == "Duplicate short code."


async def test_success_returns_the_short_url(monkeypatch: pytest.MonkeyPatch) -> None:
    data, calls = await _run(monkeypatch, _Resp(payload={"shorturl": "https://is.gd/ab12cd"}))
    assert data["shorturl"] == "https://is.gd/ab12cd"
    assert calls[0]["params"] == {"format": "json", "url": "https://example.com/a"}


async def test_non_http_input_is_rejected_without_a_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_short_link()
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(mod.httpx, "Client", _client_class(_Resp(payload={"shorturl": "x"}), calls))
    envelope = json.loads(await mod.make_short_link("ftp://example.com/a"))
    assert envelope["data"]["error"] == "invalid url"
    assert calls == []
