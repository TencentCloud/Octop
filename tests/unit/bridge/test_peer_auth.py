"""Unit tests for peer URL normalization / SSRF guards."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.i18n import error_message
from octop.infra.bridge.manager import (
    _annotate_bridge_dial_error,
    _should_refresh_peer_token,
    bridge_failure_from_dial,
    dial_error_note,
    error_from_dial_note,
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


class _Close:
    def __init__(self, code: int, reason: str) -> None:
        self.code = code
        self.reason = reason

    def __str__(self) -> str:
        return f"{self.code} (private use) {self.reason}"


class _Closed(Exception):
    def __init__(self, code: int, reason: str) -> None:
        frame = _Close(code, reason)
        self.rcvd = frame
        self.sent = frame
        super().__init__(f"received {frame}; then sent {frame}")


def test_dial_close_owned_by_another_user_is_readable() -> None:
    exc = _Closed(4003, "connection owned by another user")
    err = bridge_failure_from_dial(exc)
    assert err.code == ErrorCode.BRIDGE_PEER_CONNECTION_OWNED
    assert "4003" not in dial_error_note(exc)
    assert dial_error_note(exc) == "octop:apiErrors.BRIDGE_PEER_CONNECTION_OWNED"


def test_dial_close_permission_required_is_not_admin_only() -> None:
    exc = _Closed(4003, "permission required")
    err = bridge_failure_from_dial(exc)
    assert err.code == ErrorCode.BRIDGE_PEER_FORBIDDEN
    text = error_message(err.code.value, "zh")
    assert "权限" in text
    assert "管理员" in text


def test_connection_limit_note_keeps_the_limit() -> None:
    exc = _Closed(4008, "connection limit")
    note = dial_error_note(exc)
    err = error_from_dial_note(note)
    assert err is not None
    assert err.code == ErrorCode.BRIDGE_CONNECTION_LIMIT
    assert err.details["limit"] == 10
    text = error_message(err.code.value, "zh", **err.details)
    assert "10" in text
    assert "{limit}" not in text


@pytest.mark.asyncio
async def test_permanent_dial_stops_without_reconnect_backoff() -> None:
    from octop.infra.bridge.manager import BridgeManager
    from octop.infra.db.repos.bridge_connections import BridgeConnectionRow

    row = BridgeConnectionRow(
        pk=1,
        connection_id="cid1",
        owner_user_id=1,
        peer_base_url="https://peer.example",
        peer_username="alice",
        display_name="云端",
        notes=None,
        icon_name=None,
        credential_blob=b"enc",
        access_token_blob=b"tok",
        token_expires_at=None,
        status="connecting",
        last_error=None,
        last_seen_at=None,
        auto_reconnect=True,
        created_at=1,
        updated_at=1,
    )
    repo = MagicMock()
    repo.get.return_value = row
    mgr = BridgeManager(
        bridge_repo=repo,
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://local.test",
    )
    mgr._ensure_peer_token = AsyncMock(return_value="tok")  # type: ignore[method-assign]

    async def reject(*_args: object, **_kwargs: object) -> None:
        raise _Closed(4003, "permission required")

    mgr._run_outbound_client = reject  # type: ignore[method-assign]
    started = asyncio.get_running_loop().time()
    await asyncio.wait_for(mgr._outbound_supervisor("cid1"), timeout=1.0)
    assert asyncio.get_running_loop().time() - started < 0.5
    assert "cid1" in mgr._user_stopped
    repo.set_auto_reconnect.assert_not_called()
    repo.update_status.assert_any_call(
        "cid1",
        status="error",
        last_error="octop:apiErrors.BRIDGE_PEER_FORBIDDEN",
    )


def test_is_self_peer_url_matches_loopback_aliases() -> None:
    assert is_self_peer_url("http://localhost:8787", "http://127.0.0.1:8787")
    assert not is_self_peer_url("https://peer.example", "http://127.0.0.1:8787")
    assert not is_self_peer_url("http://127.0.0.1:8787", "")
