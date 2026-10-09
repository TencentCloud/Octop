"""Unit tests for peer URL normalization / SSRF guards."""

from __future__ import annotations

import pytest

from octop.infra.bridge.peer_auth import (
    is_self_peer_url,
    normalize_peer_base_url,
    peer_identity_key,
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


def test_is_self_peer_url_matches_loopback_aliases() -> None:
    assert is_self_peer_url("http://localhost:8787", "http://127.0.0.1:8787")
    assert not is_self_peer_url("https://peer.example", "http://127.0.0.1:8787")
    assert not is_self_peer_url("http://127.0.0.1:8787", "")
