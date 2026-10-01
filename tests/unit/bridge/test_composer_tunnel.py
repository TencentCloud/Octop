"""Unit tests for BridgeManager composer tunnel helpers."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from octop.infra.bridge.manager import BridgeManager
from octop.infra.errors import ErrorCode, OctopError


def _mgr() -> BridgeManager:
    return BridgeManager(
        bridge_repo=MagicMock(),
        secret_repo=MagicMock(),
        user_repo=MagicMock(),
        advertise_base_url="http://local.test",
    )


def _json_response(payload: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


@pytest.mark.asyncio
async def test_list_remote_resolved_models() -> None:
    mgr = _mgr()
    mgr.tunnel_http = AsyncMock(  # type: ignore[method-assign]
        return_value=_json_response(
            [{"provider_name": "openai", "model": "gpt-4o", "enabled": True}]
        )
    )
    out = await mgr.list_remote_resolved_models("cid1", owner_user_id=1)
    assert out[0]["model"] == "gpt-4o"
    mgr.tunnel_http.assert_awaited_once_with(
        connection_id="cid1",
        owner_user_id=1,
        method="GET",
        path="/api/providers/resolved",
        query="",
    )


@pytest.mark.asyncio
async def test_list_remote_knowledge_bases() -> None:
    mgr = _mgr()
    mgr.tunnel_http = AsyncMock(  # type: ignore[method-assign]
        return_value=_json_response([{"id": "kb_1", "name": "Docs"}])
    )
    out = await mgr.list_remote_knowledge_bases("cid1", owner_user_id=1)
    assert out[0]["id"] == "kb_1"
    mgr.tunnel_http.assert_awaited_once_with(
        connection_id="cid1",
        owner_user_id=1,
        method="GET",
        path="/api/knowledge-bases",
        query="",
    )


@pytest.mark.asyncio
async def test_get_remote_browser_sessions() -> None:
    mgr = _mgr()
    mgr.tunnel_http = AsyncMock(  # type: ignore[method-assign]
        return_value=_json_response({"ok": True, "environment": "desktop", "sessions": []})
    )
    out = await mgr.get_remote_browser_sessions("cid1", owner_user_id=1)
    assert out["ok"] is True
    mgr.tunnel_http.assert_awaited_once_with(
        connection_id="cid1",
        owner_user_id=1,
        method="GET",
        path="/api/browser/harness-sessions",
        query="",
    )


@pytest.mark.asyncio
async def test_post_remote_browser_handoff() -> None:
    mgr = _mgr()
    mgr.tunnel_http = AsyncMock(  # type: ignore[method-assign]
        return_value=_json_response({"ok": True, "session": {"session_id": "user-1"}})
    )
    out = await mgr.post_remote_browser_handoff(
        "cid1",
        owner_user_id=1,
        session_id="user-1",
        body={"target": "user", "reason": "user_button"},
    )
    assert out["ok"] is True
    call = mgr.tunnel_http.await_args
    assert call.kwargs["method"] == "POST"
    assert call.kwargs["path"] == "/api/browser/sessions/user-1/handoff"


@pytest.mark.asyncio
async def test_tunnel_http_denies_disallowed_path() -> None:
    mgr = _mgr()
    mgr.get_owned = MagicMock(return_value=MagicMock())  # type: ignore[method-assign]
    with pytest.raises(OctopError) as exc:
        await mgr.tunnel_http(
            connection_id="cid1",
            owner_user_id=1,
            method="GET",
            path="/api/agents/main/skill-packages",
        )
    assert exc.value.code == ErrorCode.BRIDGE_REMOTE_UNSUPPORTED


@pytest.mark.asyncio
async def test_tunnel_json_get_rejects_http_error() -> None:
    mgr = _mgr()
    mgr.tunnel_http = AsyncMock(  # type: ignore[method-assign]
        return_value=httpx.Response(502, text="boom")
    )
    with pytest.raises(OctopError) as exc:
        await mgr.get_remote_knowledge_capability("cid1", owner_user_id=1)
    assert exc.value.code == ErrorCode.BRIDGE_TUNNEL_FAILED
