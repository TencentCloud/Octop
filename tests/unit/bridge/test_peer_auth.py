"""Unit tests for peer URL normalization / SSRF guards."""

from __future__ import annotations

import pytest

from octop.infra.bridge.manager import (
    _annotate_bridge_dial_error,
    _should_refresh_peer_token,
)
from octop.infra.bridge.peer_auth import (
    is_self_peer_url,
    normalize_peer_base_url,
    peer_identity_key,
    peer_ws_url,
)
from octop.infra.errors import ErrorCode, OctopError


def test_normalize_accepts_https_host() -> None:
    assert normalize_peer_base_url("https://demo.octop.chat/") == "https://demo.octop.chat"


def test_normalize_rejects_metadata_ip() -> None:
    with pytest.raises(OctopError) as ei:
        normalize_peer_base_url("http://169.254.169.254/latest/meta-data")
    assert ei.value.code == ErrorCode.BRIDGE_PEER_UNREACHABLE


def test_normalize_rejects_non_http() -> None:
    with pytest.raises(OctopError) as ei:
        normalize_peer_base_url("ftp://peer.example")
    assert ei.value.code == ErrorCode.BRIDGE_PEER_UNREACHABLE


def test_peer_identity_collapses_localhost_and_username_case() -> None:
    assert peer_identity_key("http://localhost:8787/", "Alice") == peer_identity_key(
        "http://127.0.0.1:8787", "alice"
    )


def test_peer_ws_url_quotes_token() -> None:
    url = peer_ws_url("https://203.0.113.10", token="a+b/c==")
    assert url == "wss://203.0.113.10/api/bridge/ws?token=a%2Bb%2Fc%3D%3D"


def test_http_403_is_a_rejected_token_not_a_missing_route() -> None:
    class _Rejected(Exception):
        def __init__(self) -> None:
            super().__init__("server rejected WebSocket connection: HTTP 403")
            self.response = type("Resp", (), {"status_code": 403})()

    exc = _Rejected()
    assert _should_refresh_peer_token(exc)
    text = _annotate_bridge_dial_error(exc)
    assert "HTTP 403" in text
    assert "rejected token" in text
    assert "needs Octop with /api/bridge/ws" not in text


def test_is_self_peer_url_matches_loopback_aliases() -> None:
    assert is_self_peer_url("http://localhost:8787", "http://127.0.0.1:8787")
    assert not is_self_peer_url("https://peer.example", "http://127.0.0.1:8787")
    assert not is_self_peer_url("http://127.0.0.1:8787", "")
