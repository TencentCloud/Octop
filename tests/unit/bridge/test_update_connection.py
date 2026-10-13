"""Unit tests for BridgeManager.update_connection_meta endpoint edits."""

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
        "connection_id": "cid1",
        "owner_user_id": 1,
        "peer_base_url": "https://peer.example",
        "peer_username": "alice",
        "display_name": "云端",
        "notes": None,
        "icon_name": None,
        "credential_blob": b"enc-pass",
        "access_token_blob": b"enc-token",
        "token_expires_at": None,
        "status": "connected",
        "last_error": None,
        "last_seen_at": None,
        "auto_reconnect": True,
        "created_at": 1,
        "updated_at": 1,
    }
    base.update(overrides)
    return BridgeConnectionRow(**base)  # type: ignore[arg-type]


def _mgr() -> BridgeManager:
    return BridgeManager(
        bridge_repo=MagicMock(),
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://local.test",
    )


@pytest.mark.asyncio
async def test_update_meta_only_skips_reauth(monkeypatch: pytest.MonkeyPatch) -> None:
    mgr = _mgr()
    row = _row()
    updated = _row(display_name="新名", notes="n1")
    mgr.get_owned = MagicMock(return_value=row)  # type: ignore[method-assign]
    mgr._repo.find_by_display_name = MagicMock(return_value=None)
    mgr._repo.update_settings = MagicMock(return_value=updated)
    login = AsyncMock()
    monkeypatch.setattr("octop.infra.bridge.manager.login_peer", login)

    out = await mgr.update_connection_meta(
        "cid1",
        owner_user_id=1,
        display_name="新名",
        notes="n1",
        update_notes=True,
        peer_base_url="https://peer.example",
        peer_username="alice",
        password="",
    )
    assert out.display_name == "新名"
    login.assert_not_awaited()
    mgr._repo.update_settings.assert_called_once()
    assert mgr._repo.update_settings.call_args.kwargs.get("update_credentials") is not True


@pytest.mark.asyncio
async def test_update_endpoint_reauths_and_reconnects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mgr = _mgr()
    row = _row()
    after = _row(peer_base_url="https://other.example", peer_username="bob")
    mgr.get_owned = MagicMock(return_value=row)  # type: ignore[method-assign]
    mgr._repo.find_by_display_name = MagicMock(return_value=None)
    mgr._repo.list_for_owner = MagicMock(return_value=[])
    mgr._repo.update_settings = MagicMock(return_value=after)
    mgr._repo.get = MagicMock(return_value=after)
    mgr.disconnect = AsyncMock()  # type: ignore[method-assign]
    mgr.connect = AsyncMock(return_value=after)  # type: ignore[method-assign]
    login = AsyncMock(return_value={"access_token": "tok", "expires_in": 3600})
    monkeypatch.setattr("octop.infra.bridge.manager.login_peer", login)
    monkeypatch.setattr(
        "octop.infra.bridge.manager.normalize_peer_base_url",
        lambda raw: raw.strip().rstrip("/"),
    )
    monkeypatch.setattr(
        "octop.infra.bridge.manager.encrypt_payload",
        lambda _repo, payload: f"enc:{payload}".encode(),
    )
    monkeypatch.setattr(
        "octop.infra.bridge.manager.decrypt_payload",
        lambda _repo, _blob: {"password": "old-secret"},
    )

    out = await mgr.update_connection_meta(
        "cid1",
        owner_user_id=1,
        display_name="云端",
        peer_base_url="https://other.example",
        peer_username="bob",
        password=None,
    )
    assert out.peer_base_url == "https://other.example"
    login.assert_awaited_once()
    assert login.await_args.kwargs["username"] == "bob"
    assert login.await_args.kwargs["password"] == "old-secret"
    mgr.disconnect.assert_awaited_once_with("cid1")
    mgr.connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_endpoint_rejects_duplicate_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mgr = _mgr()
    row = _row()
    other = _row(
        connection_id="cid2",
        display_name="另一台",
        peer_base_url="https://other.example",
        peer_username="bob",
    )
    mgr.get_owned = MagicMock(return_value=row)  # type: ignore[method-assign]
    mgr._repo.find_by_display_name = MagicMock(return_value=None)
    mgr._repo.list_for_owner = MagicMock(return_value=[row, other])
    monkeypatch.setattr(
        "octop.infra.bridge.manager.normalize_peer_base_url",
        lambda raw: raw.strip().rstrip("/"),
    )
    with pytest.raises(OctopError) as ei:
        await mgr.update_connection_meta(
            "cid1",
            owner_user_id=1,
            peer_base_url="https://other.example/",
            peer_username="Bob",
            password="secret",
        )
    assert ei.value.code == ErrorCode.BRIDGE_PEER_ALREADY_LINKED
    mgr._repo.update_settings.assert_not_called()


def test_connection_public_marks_inbound() -> None:
    mgr = _mgr()
    inbound = mgr.connection_public(_row(credential_blob=None))
    assert inbound["inbound"] is True
    assert inbound["has_password"] is False
    outbound = mgr.connection_public(_row())
    assert outbound["inbound"] is False
    assert outbound["has_password"] is True


@pytest.mark.asyncio
async def test_update_password_required_when_no_stored_secret() -> None:
    mgr = _mgr()
    row = _row(credential_blob=None)
    mgr.get_owned = MagicMock(return_value=row)  # type: ignore[method-assign]
    mgr._repo.find_by_display_name = MagicMock(return_value=None)
    with pytest.raises(OctopError) as ei:
        await mgr.update_connection_meta(
            "cid1",
            owner_user_id=1,
            peer_base_url="https://other.example",
            password="",
        )
    assert ei.value.code == ErrorCode.BRIDGE_INBOUND_PASSIVE


@pytest.mark.asyncio
async def test_inbound_update_display_only() -> None:
    mgr = _mgr()
    row = _row(credential_blob=None, auto_reconnect=False)
    updated = _row(credential_blob=None, display_name="对端机", notes="n")
    mgr.get_owned = MagicMock(return_value=row)  # type: ignore[method-assign]
    mgr._repo.find_by_display_name = MagicMock(return_value=None)
    mgr._repo.update_settings = MagicMock(return_value=updated)
    out = await mgr.update_connection_meta(
        "cid1",
        owner_user_id=1,
        display_name="对端机",
        notes="n",
        update_notes=True,
        peer_base_url=row.peer_base_url,
        peer_username=row.peer_username,
        password="",
    )
    assert out.display_name == "对端机"
    mgr._repo.update_settings.assert_called_once()


@pytest.mark.asyncio
async def test_inbound_connect_rejected() -> None:
    mgr = _mgr()
    mgr.get_owned = MagicMock(return_value=_row(credential_blob=None))  # type: ignore[method-assign]
    with pytest.raises(OctopError) as ei:
        await mgr.connect("cid1", owner_user_id=1)
    assert ei.value.code == ErrorCode.BRIDGE_INBOUND_PASSIVE


@pytest.mark.asyncio
async def test_inbound_auto_reconnect_rejected() -> None:
    mgr = _mgr()
    mgr.get_owned = MagicMock(return_value=_row(credential_blob=None))  # type: ignore[method-assign]
    with pytest.raises(OctopError) as ei:
        await mgr.set_auto_reconnect("cid1", owner_user_id=1, enabled=True)
    assert ei.value.code == ErrorCode.BRIDGE_INBOUND_PASSIVE


@pytest.mark.asyncio
async def test_delete_notifies_peer_before_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mgr = _mgr()
    mgr.get_owned = MagicMock(return_value=_row())  # type: ignore[method-assign]
    sess = MagicMock()
    sess.closed = False
    sess.send_json = AsyncMock()
    mgr._sessions["cid1"] = sess
    mgr.disconnect = AsyncMock()  # type: ignore[method-assign]
    monkeypatch.setattr("octop.infra.bridge.manager.asyncio.sleep", AsyncMock())
    await mgr.delete_connection("cid1", owner_user_id=1)
    sess.send_json.assert_awaited_once_with({"type": "close", "reason": "deleted"})
    mgr.disconnect.assert_awaited_once_with("cid1")
    mgr._repo.delete.assert_called_once_with("cid1")


@pytest.mark.asyncio
async def test_finalize_inbound_offline_keeps_row() -> None:
    from octop.infra.bridge.transport import BridgeSession

    mgr = _mgr()
    mgr._repo.get = MagicMock(return_value=_row(credential_blob=None))
    sess = BridgeSession(connection_id="cid1", send_text=AsyncMock())
    await mgr._finalize_inbound("cid1", sess)
    mgr._repo.delete.assert_not_called()
    mgr._repo.update_status.assert_called_once()


@pytest.mark.asyncio
async def test_finalize_inbound_deleted_drops_row() -> None:
    from octop.infra.bridge.transport import BridgeSession

    mgr = _mgr()
    sess = BridgeSession(connection_id="cid1", send_text=AsyncMock())
    sess.close_reason = "deleted"
    await mgr._finalize_inbound("cid1", sess)
    mgr._repo.delete.assert_called_once_with("cid1")
    mgr._repo.update_status.assert_not_called()


def test_inbound_default_display_name_skips_url_and_id() -> None:
    from octop.infra.bridge.manager import inbound_default_display_name

    assert (
        inbound_default_display_name(
            connection_id="cid1",
            preferred_name="https://192.168.1.8:8787",
            peer_username="alice",
        )
        == "alice"
    )
    assert (
        inbound_default_display_name(
            connection_id="cid1",
            preferred_name="10.0.0.1",
            peer_username="bob",
        )
        == "bob"
    )
    assert (
        inbound_default_display_name(
            connection_id="cid1",
            preferred_name="笔记本",
            peer_username="alice",
            existing_name="https://peer.example",
        )
        == "笔记本"
    )
    assert (
        inbound_default_display_name(
            connection_id="cid1",
            preferred_name="new",
            existing_name="我改过的名",
        )
        == "我改过的名"
    )
    assert inbound_default_display_name(connection_id="cid1") == "cid1"
