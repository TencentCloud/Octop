"""Unit tests for Bridge peer probe summaries."""

from __future__ import annotations

import pytest

from octop.infra.bridge.manager import _absolute_peer_url, _probe_agent_summary


def test_absolute_peer_url_joins_relative_icon() -> None:
    assert (
        _absolute_peer_url("https://demo.octop.chat", "/api/agents/abc/icon")
        == "https://demo.octop.chat/api/agents/abc/icon"
    )


def test_absolute_peer_url_keeps_absolute() -> None:
    url = "https://cdn.example/icon.png"
    assert _absolute_peer_url("https://demo.octop.chat", url) == url


def test_absolute_peer_url_empty() -> None:
    assert _absolute_peer_url("https://demo.octop.chat", None) is None
    assert _absolute_peer_url("https://demo.octop.chat", "  ") is None


def test_probe_agent_summary_maps_fields() -> None:
    summary = _probe_agent_summary(
        {
            "agent_id": "01AGENT",
            "id": 42,
            "name": "Demo Expert",
            "description": "Helps with demos",
            "icon_url": "/experts/avatars/scene-healthcare.svg",
            "icon_name": "heart",
            "color": "#3366ff",
            "state": "running",
            "kind": "expert",
        },
        peer_base_url="https://demo.octop.chat",
    )
    assert summary == {
        "agent_id": "01AGENT",
        "name": "Demo Expert",
        "description": "Helps with demos",
        "icon_url": "/experts/avatars/scene-healthcare.svg",
        "icon_name": "heart",
        "color": "#3366ff",
        "state": "running",
        "kind": "expert",
    }


def test_probe_agent_summary_drops_peer_avatar_without_connection() -> None:
    summary = _probe_agent_summary(
        {
            "agent_id": "01AGENT",
            "icon_url": "/api/agents/01AGENT/icon",
            "name": "Demo Expert",
        },
        peer_base_url="https://demo.octop.chat",
    )
    assert summary["icon_url"] is None


def test_probe_agent_summary_rewrites_avatar_when_connected() -> None:
    summary = _probe_agent_summary(
        {
            "agent_id": "01AGENT",
            "icon_url": "/api/agents/01AGENT/avatar",
            "name": "Demo Expert",
        },
        peer_base_url="https://demo.octop.chat",
        connection_id="01CID",
    )
    assert summary["icon_url"] == "/api/agents/bridge:01CID:01AGENT/avatar"


def test_probe_agent_summary_prefers_agent_id_over_int_id() -> None:
    summary = _probe_agent_summary(
        {"id": 7, "agent_id": "public-id", "name": "X"},
        peer_base_url="https://peer.example",
    )
    assert summary["agent_id"] == "public-id"
    assert summary["description"] is None
    assert summary["icon_url"] is None


@pytest.mark.asyncio
async def test_probe_owned_uses_stored_password(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import AsyncMock, MagicMock

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
        access_token_blob=None,
        token_expires_at=None,
        status="disconnected",
        last_error=None,
        last_seen_at=None,
        auto_reconnect=True,
        created_at=1,
        updated_at=1,
    )
    mgr = BridgeManager(
        bridge_repo=MagicMock(),
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://local.test",
    )
    mgr.get_owned = MagicMock(return_value=row)  # type: ignore[method-assign]
    monkeypatch.setattr(
        "octop.infra.bridge.manager.decrypt_payload",
        lambda _secrets, _blob: {"password": "stored-secret"},
    )
    probe = AsyncMock(return_value={"agent_count": 0, "agents": []})
    mgr.probe_peer = probe  # type: ignore[method-assign]
    await mgr.probe_owned_connection(
        "cid1",
        owner_user_id=1,
        peer_base_url="https://peer.example",
        peer_username="alice",
        password="",
    )
    assert probe.await_args.kwargs["password"] == "stored-secret"
    assert probe.await_args.kwargs["connection_id"] == "cid1"


@pytest.mark.asyncio
async def test_probe_owned_prefers_typed_password(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import AsyncMock, MagicMock

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
        access_token_blob=None,
        token_expires_at=None,
        status="disconnected",
        last_error=None,
        last_seen_at=None,
        auto_reconnect=True,
        created_at=1,
        updated_at=1,
    )
    mgr = BridgeManager(
        bridge_repo=MagicMock(),
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://local.test",
    )
    mgr.get_owned = MagicMock(return_value=row)  # type: ignore[method-assign]
    decrypt = MagicMock()
    monkeypatch.setattr("octop.infra.bridge.manager.decrypt_payload", decrypt)
    probe = AsyncMock(return_value={"agent_count": 0, "agents": []})
    mgr.probe_peer = probe  # type: ignore[method-assign]
    await mgr.probe_owned_connection(
        "cid1",
        owner_user_id=1,
        peer_base_url="https://other.example",
        peer_username="bob",
        password="typed-secret",
    )
    decrypt.assert_not_called()
    assert probe.await_args.kwargs["password"] == "typed-secret"
    assert probe.await_args.kwargs["peer_username"] == "bob"


@pytest.mark.asyncio
async def test_probe_peer_auth_failed_raises_400_status(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from octop.infra.bridge.manager import BridgeManager
    from octop.infra.errors import ErrorCode, OctopError

    mgr = BridgeManager(
        bridge_repo=MagicMock(),
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://127.0.0.1:8080",
    )
    monkeypatch.setattr(
        "octop.infra.bridge.manager.login_peer",
        AsyncMock(side_effect=OctopError(ErrorCode.BRIDGE_AUTH_FAILED, "peer rejected credentials")),
    )
    with pytest.raises(OctopError) as exc_info:
        await mgr.probe_peer(
            peer_base_url="http://127.0.0.1:9000",
            peer_username="alice",
            password="wrong-password",
        )
    assert exc_info.value.code is ErrorCode.BRIDGE_AUTH_FAILED
    assert exc_info.value.status == 400


@pytest.mark.asyncio
async def test_probe_peer_missing_credentials_raises_400() -> None:
    from unittest.mock import MagicMock

    from octop.infra.bridge.manager import BridgeManager
    from octop.infra.errors import ErrorCode, OctopError

    mgr = BridgeManager(
        bridge_repo=MagicMock(),
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://127.0.0.1:8080",
    )
    with pytest.raises(OctopError) as exc_info:
        await mgr.probe_peer(
            peer_base_url="http://127.0.0.1:9000",
            peer_username="",
            password="",
        )
    assert exc_info.value.code is ErrorCode.BRIDGE_AUTH_FAILED
    assert exc_info.value.status == 400


@pytest.mark.asyncio
async def test_probe_peer_agents_unauthorized_raises_400(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from octop.infra.bridge.manager import BridgeManager
    from octop.infra.errors import ErrorCode, OctopError

    fake_resp = MagicMock()
    fake_resp.status_code = 401
    fake_resp.text = "Unauthorized"

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=fake_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    mgr = BridgeManager(
        bridge_repo=MagicMock(),
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://127.0.0.1:8080",
    )
    monkeypatch.setattr(
        "octop.infra.bridge.manager.login_peer",
        AsyncMock(return_value={"access_token": "valid-token", "user": {}}),
    )
    monkeypatch.setattr("octop.infra.bridge.manager.httpx.AsyncClient", lambda *a, **k: mock_client)

    with pytest.raises(OctopError) as exc_info:
        await mgr.probe_peer(
            peer_base_url="http://127.0.0.1:9000",
            peer_username="alice",
            password="password",
        )
    assert exc_info.value.code is ErrorCode.BRIDGE_AUTH_FAILED
    assert exc_info.value.status == 400

