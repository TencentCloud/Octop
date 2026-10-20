"""Tests for agent-fetch SSRF guard and web_fetch private-target blocking."""

from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest

from octop_harness.builtin.tools.web_fetch import web_fetch
from octop_harness.security.ssrf import UnsafeAgentFetchUrlError, validate_agent_fetch_url

_web_fetch_mod = importlib.import_module("octop_harness.builtin.tools.web_fetch")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/secret",
        "http://localhost/secret",
        "https://10.0.0.1/x",
        "http://192.168.1.1/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data",
        "http://host.docker.internal:8080/",
        "http://nas.local/api",
    ],
)
def test_validate_agent_fetch_url_blocks_private_targets(url: str) -> None:
    with pytest.raises(UnsafeAgentFetchUrlError, match="private or local"):
        validate_agent_fetch_url(url)


def test_validate_agent_fetch_url_accepts_public_literal(monkeypatch: pytest.MonkeyPatch) -> None:
    # 8.8.8.8 is public; no DNS lookup needed.
    assert validate_agent_fetch_url("https://8.8.8.8/resolve") == "https://8.8.8.8/resolve"


def test_validate_agent_fetch_url_rejects_hostname_resolving_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_getaddrinfo(*_args: object, **_kwargs: object) -> list[tuple]:
        return [(None, None, None, None, ("10.1.2.3", 80))]

    monkeypatch.setattr("octop_harness.security.ssrf.socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeAgentFetchUrlError, match="private or local"):
        validate_agent_fetch_url("https://evil.example.com/x")


def test_web_fetch_blocks_lan_without_http_call() -> None:
    with patch.object(_web_fetch_mod.httpx, "Client") as client_cls:
        result = web_fetch.invoke({"url": "http://192.168.0.5/admin"})
    assert result.startswith("Error:")
    assert "private or local" in result
    client_cls.assert_not_called()


def test_web_fetch_blocks_redirect_to_private(monkeypatch: pytest.MonkeyPatch) -> None:
    def guard(url: str) -> str:
        if "10.0.0.1" in url:
            raise UnsafeAgentFetchUrlError("private or local network addresses are not allowed")
        return url

    monkeypatch.setattr(_web_fetch_mod, "validate_agent_fetch_url", guard)

    class RedirectResponse:
        status_code = 302
        is_error = False
        headers = {"location": "http://10.0.0.1/secret"}
        content = b""
        text = ""
        request = type("Req", (), {"url": "https://example.com/go"})()

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def get(self, url: str) -> RedirectResponse:
            assert url.startswith("https://example.com")
            return RedirectResponse()

    with patch.object(_web_fetch_mod.httpx, "Client", FakeClient):
        result = web_fetch.invoke({"url": "https://example.com/go"})

    assert result.startswith("Error:")
    assert "private or local" in result


def test_web_fetch_html_still_works_with_public_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_web_fetch_mod, "validate_agent_fetch_url", lambda u: u)
    html = "<html><body><h1>Title</h1></body></html>"

    class FakeResponse:
        status_code = 200
        is_error = False
        content = html.encode("utf-8")
        text = html
        headers = {"content-type": "text/html; charset=utf-8"}
        request = type("Req", (), {"url": "https://example.com"})()

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            assert kwargs.get("follow_redirects") is False

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def get(self, url: str) -> FakeResponse:
            return FakeResponse()

    with patch.object(_web_fetch_mod.httpx, "Client", FakeClient):
        md = web_fetch.invoke({"url": "https://example.com"})
    assert "Title" in md
