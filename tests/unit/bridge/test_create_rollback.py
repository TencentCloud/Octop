"""BridgeManager create_connection rollback behavior."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from octop.infra.bridge.manager import BridgeManager
from octop.infra.db.repos.bridge_connections import BridgeConnectionRow
from octop.infra.errors import ErrorCode, OctopError


def _row(**overrides: Any) -> BridgeConnectionRow:
    base = {
        "pk": 1,
        "connection_id": "01CONN",
        "owner_user_id": 1,
        "peer_base_url": "https://peer.example",
        "peer_username": "bob",
        "display_name": "Cloud",
        "notes": None,
        "icon_name": None,
        "credential_blob": b"x",
        "access_token_blob": b"y",
        "token_expires_at": None,
        "status": "connecting",
        "last_error": None,
        "last_seen_at": None,
        "auto_reconnect": True,
        "created_at": 1,
        "updated_at": 1,
    }
    base.update(overrides)
    return BridgeConnectionRow(**base)


@pytest.mark.asyncio
async def test_create_connection_rolls_back_when_connect_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = MagicMock()
    repo.find_by_display_name.return_value = None
    created = _row()
    repo.create.return_value = created
    repo.get.return_value = None
    repo.get_for_owner.return_value = created
    mgr = BridgeManager(
        bridge_repo=repo,
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://local.test",
    )
    monkeypatch.setattr(
        "octop.infra.bridge.manager.normalize_peer_base_url",
        lambda url: url.rstrip("/"),
    )
    monkeypatch.setattr(
        "octop.infra.bridge.manager.new_short_id",
        lambda: "01CONN",
    )
    monkeypatch.setattr(
        "octop.infra.bridge.manager.login_peer",
        AsyncMock(return_value={"access_token": "tok", "expires_in": 3600}),
    )
    monkeypatch.setattr(
        "octop.infra.bridge.manager.encrypt_payload",
        lambda _s, _p: b"enc",
    )
    mgr.connect = AsyncMock(  # type: ignore[method-assign]
        side_effect=OctopError(ErrorCode.BRIDGE_PEER_UNREACHABLE, "ws failed")
    )
    mgr.disconnect = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(OctopError) as ei:
        await mgr.create_connection(
            owner_user_id=1,
            peer_base_url="https://peer.example",
            peer_username="bob",
            password="secret",
            display_name="Cloud",
            connect=True,
        )
    assert ei.value.code == ErrorCode.BRIDGE_PEER_UNREACHABLE
    repo.delete.assert_called_once_with("01CONN")
    mgr.disconnect.assert_awaited()


@pytest.mark.asyncio
async def test_create_connection_rejects_taken_display_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = MagicMock()
    repo.find_by_display_name.return_value = _row()
    mgr = BridgeManager(
        bridge_repo=repo,
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://local.test",
    )
    monkeypatch.setattr(
        "octop.infra.bridge.manager.normalize_peer_base_url",
        lambda url: url.rstrip("/"),
    )
    with pytest.raises(OctopError) as ei:
        await mgr.create_connection(
            owner_user_id=1,
            peer_base_url="https://peer.example",
            peer_username="bob",
            password="secret",
            display_name="Cloud",
            connect=True,
        )
    assert ei.value.code == ErrorCode.BRIDGE_DISPLAY_NAME_TAKEN
    repo.create.assert_not_called()
