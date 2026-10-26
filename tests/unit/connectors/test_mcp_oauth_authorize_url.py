"""MCP OAuth authorize URL keeps endpoint-owned query params (RFC 6749 §3.1).

Regression for #2391: endpoints like ``?tenant=acme`` used to be corrupted
into ``tenant=acme?response_type=code``, losing ``response_type``.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from octop.infra.connectors.oauth.mcp import build_authorize_url


def _build(endpoint: str, **overrides: str) -> dict[str, list[str]]:
    kwargs = {
        "client_id": "demo-client",
        "redirect_uri": "https://client.example/callback",
        "state": "demo-state",
        "code_challenge": "demo-challenge",
    }
    kwargs.update(overrides)
    url = build_authorize_url({"authorization_endpoint": endpoint}, **kwargs)
    return parse_qs(urlsplit(url).query)


def test_plain_endpoint_receives_oauth_params() -> None:
    query = _build("https://auth.example.com/authorize")
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["demo-client"]
    assert query["code_challenge_method"] == ["S256"]


def test_endpoint_query_params_preserved_and_merged() -> None:
    query = _build("https://auth.example.com/authorize?tenant=acme")
    assert query["tenant"] == ["acme"]
    assert query["response_type"] == ["code"]
    assert query["state"] == ["demo-state"]


def test_multiple_endpoint_params_preserved() -> None:
    query = _build("https://auth.example.com/authorize?tenant=acme&domain=eu")
    assert query["tenant"] == ["acme"]
    assert query["domain"] == ["eu"]
    assert query["response_type"] == ["code"]


def test_encoded_endpoint_param_round_trips() -> None:
    query = _build("https://auth.example.com/authorize?next=%2Fdeep%2Fpath")
    assert query["next"] == ["/deep/path"]


def test_optional_scope_and_resource_included() -> None:
    query = _build(
        "https://auth.example.com/authorize?tenant=acme",
        scope="read write",
        resource="https://mcp.example.com",
    )
    assert query["scope"] == ["read write"]
    assert query["resource"] == ["https://mcp.example.com"]
    assert query["tenant"] == ["acme"]


def test_oauth_params_win_on_key_collision() -> None:
    query = _build("https://auth.example.com/authorize?state=stale")
    assert query["state"] == ["demo-state"]


def test_endpoint_fragment_stays_at_the_end() -> None:
    url = build_authorize_url(
        {"authorization_endpoint": "https://auth.example.com/authorize?tenant=acme#frag"},
        client_id="demo-client",
        redirect_uri="https://client.example/callback",
        state="demo-state",
        code_challenge="demo-challenge",
    )
    split = urlsplit(url)
    assert split.fragment == "frag"
    assert parse_qs(split.query)["tenant"] == ["acme"]
