"""tests/unit/api/test_internal_mcp_active_only.py

The internal MCP endpoints are opened by an Octop-hosted connector gateway with a
long-lived internal token.  Disabling the connector instance is the user's off
switch, so every verb on the session must stop answering, not just POST.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.responses import JSONResponse, Response, StreamingResponse

from octop.api.routers import internal_mcp
from octop.infra.errors import ErrorCode, OctopError

INSTANCE_ID = "01INSTANCE"
KIND = "generic"
TOKEN = "internal-token"


class _Repo:
    def __init__(self, inst: SimpleNamespace | None) -> None:
        self._inst = inst

    def get(self, instance_id: str) -> SimpleNamespace | None:
        return self._inst if instance_id == INSTANCE_ID else None


class _Svc:
    def verify_internal_token(self, instance_id: str, token: str) -> dict[str, str] | None:
        if instance_id != INSTANCE_ID or token != TOKEN:
            return None
        return {"internal_token": token}


class _Request:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}


def _server(monkeypatch: pytest.MonkeyPatch, status: str | None) -> SimpleNamespace:
    """A server whose connector instance has `status` (None = the row is gone)."""
    monkeypatch.setattr(internal_mcp, "_service", lambda srv: _Svc())
    inst = None if status is None else SimpleNamespace(kind=KIND, status=status)
    repos = SimpleNamespace(connector_repo=_Repo(inst))
    return SimpleNamespace(services=SimpleNamespace(repos=repos))


async def _get(server: SimpleNamespace, **headers: str) -> object:
    return await internal_mcp.internal_mcp_get(
        KIND, INSTANCE_ID, _Request(headers or None), TOKEN, server
    )


async def test_get_of_disabled_instance_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _server(monkeypatch, "disabled")
    with pytest.raises(OctopError) as excinfo:
        await _get(server, **{internal_mcp.MCP_SESSION_HEADER: "s1"})
    assert excinfo.value.code is ErrorCode.CONNECTOR_NOT_FOUND


async def test_delete_of_disabled_instance_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _server(monkeypatch, "disabled")
    with pytest.raises(OctopError) as excinfo:
        await internal_mcp.internal_mcp_delete(KIND, INSTANCE_ID, TOKEN, server)
    assert excinfo.value.code is ErrorCode.CONNECTOR_NOT_FOUND


async def test_post_of_disabled_instance_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _server(monkeypatch, "disabled")
    with pytest.raises(OctopError) as excinfo:
        await internal_mcp.internal_mcp_post(KIND, INSTANCE_ID, _Request(), TOKEN, server)
    assert excinfo.value.code is ErrorCode.CONNECTOR_NOT_FOUND


async def test_get_with_wrong_token_is_auth_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _server(monkeypatch, "active")
    with pytest.raises(OctopError) as excinfo:
        await internal_mcp.internal_mcp_get(KIND, INSTANCE_ID, _Request(), "nope", server)
    assert excinfo.value.code is ErrorCode.AUTH_FAILED


async def test_get_of_active_instance_opens_the_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = await _get(_server(monkeypatch, "active"), **{internal_mcp.MCP_SESSION_HEADER: "s1"})
    assert isinstance(resp, StreamingResponse)


async def test_delete_of_active_instance_ends_the_session(monkeypatch: pytest.MonkeyPatch) -> None:
    server = _server(monkeypatch, "active")
    resp = await internal_mcp.internal_mcp_delete(KIND, INSTANCE_ID, TOKEN, server)
    assert isinstance(resp, Response)
    assert resp.status_code == 204


async def test_get_of_missing_instance_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(OctopError) as excinfo:
        await _get(_server(monkeypatch, None))
    assert excinfo.value.code is ErrorCode.CONNECTOR_NOT_FOUND


async def test_get_without_session_header_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = await _get(_server(monkeypatch, "active"))
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 405
