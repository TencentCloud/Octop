"""Secret-input submit endpoint: scope checks, lifecycle, and 422 non-echo."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.testclient import TestClient

import octop.api.routers.chat.routes as chat_routes
from octop.api.routers.chat.models import SecretInputSubmitBody
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.hitl.coordinator import HitlChannelCoordinator

_SECRET_MARKER = "sk-SUPER-SECRET-VALUE"
_SECRET_ACTIONS = [
    {
        "name": "request_secret_input",
        "args": {"slot": "STEAM_WEB_API_KEY", "prompt": "Steam Web API key", "title": "Steam"},
    }
]


def _request() -> Any:
    """Request stub: SSE helpers only need headers/url/is_disconnected."""
    return SimpleNamespace(
        headers={"accept-language": "en"},
        url=SimpleNamespace(path="/api/agents/agent-1/chat/secret-input/submit"),
        is_disconnected=AsyncMock(return_value=False),
    )


def _make_server(hitl: HitlChannelCoordinator) -> tuple[Any, MagicMock, MagicMock]:
    async def _resume_chunks(**_kwargs: Any):
        yield {"type": "token", "content": "stored, continuing"}
        yield {"type": "done"}

    processor = MagicMock()
    processor.hitl_coordinator = hitl
    processor.iter_hitl_resume_chunks = _resume_chunks
    secrets = MagicMock()
    registry = SimpleNamespace(agent_secrets=secrets, reload=AsyncMock(return_value=True))
    server = SimpleNamespace(
        app_runtime=SimpleNamespace(
            gateway=SimpleNamespace(
                processor=processor,
                thread_registry=SimpleNamespace(get_thread=lambda _t: None),
            ),
            agent_registry=registry,
        )
    )
    return server, secrets, registry


def _seed_pending(hitl: HitlChannelCoordinator, *, user_id: int = 1, thread_id: str = "thr-1"):
    return hitl.store.register(
        thread_id=thread_id,
        agent_id="agent-1",
        user_id=user_id,
        session_key="agent-1:dashboard:1:dm",
        channel_type="dashboard",
        action_requests=list(_SECRET_ACTIONS),
        review_configs=None,
    )


def _body(
    record, action: str = "submit", value: str | None = _SECRET_MARKER
) -> SecretInputSubmitBody:
    return SecretInputSubmitBody(
        thread_id=record.thread_id,
        pending_id=record.pending_id,
        action=action,  # type: ignore[arg-type]
        value=value,
    )


async def _drain(response: Any) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    async for raw in response.body_iterator:  # type: ignore[union-attr]
        for block in str(raw).split("\n\n"):
            line = next((ln[6:] for ln in block.split("\n") if ln.startswith("data: ")), None)
            if line:
                chunks.append(json.loads(line))
    return chunks


@pytest.mark.asyncio
async def test_submit_stores_slot_and_resumes_without_echoing_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hitl = HitlChannelCoordinator()
    record = _seed_pending(hitl)
    server, secrets, registry = _make_server(hitl)
    stored: dict[str, Any] = {}

    def _store_slot(**kwargs: Any) -> None:
        stored.update(kwargs)

    secrets.store_slot.side_effect = _store_slot
    monkeypatch.setattr(
        chat_routes,
        "require_agent_owner_row",
        lambda *_a, **_k: SimpleNamespace(user_id=1, is_shared=0),
    )
    user = SimpleNamespace(id=1, is_admin=False)

    response = await chat_routes.submit_secret_input(
        "agent-1", _body(record), _request(), user=user, server=server
    )
    chunks = await _drain(response)

    assert chunks[-1] == {"type": "done"}
    joined = json.dumps(chunks)
    assert _SECRET_MARKER not in joined
    assert stored["agent_id"] == "agent-1"
    assert stored["slot_name"] == "STEAM_WEB_API_KEY"
    assert stored["value"] == _SECRET_MARKER
    assert hitl.store.get(record.pending_id).status == "filled"  # type: ignore[union-attr]
    registry.reload.assert_awaited_once_with("agent-1")


@pytest.mark.asyncio
async def test_cancel_skips_storage_and_marks_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    hitl = HitlChannelCoordinator()
    record = _seed_pending(hitl)
    server, secrets, registry = _make_server(hitl)
    monkeypatch.setattr(
        chat_routes,
        "require_agent_owner_row",
        lambda *_a, **_k: SimpleNamespace(user_id=1, is_shared=0),
    )
    user = SimpleNamespace(id=1, is_admin=False)

    response = await chat_routes.submit_secret_input(
        "agent-1", _body(record, action="cancel", value=None), _request(), user=user, server=server
    )
    chunks = await _drain(response)

    assert chunks[-1] == {"type": "done"}
    secrets.store_slot.assert_not_called()
    registry.reload.assert_not_called()
    assert hitl.store.get(record.pending_id).status == "cancelled"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_replayed_submit_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    hitl = HitlChannelCoordinator()
    record = _seed_pending(hitl)
    server, secrets, _registry = _make_server(hitl)
    monkeypatch.setattr(
        chat_routes,
        "require_agent_owner_row",
        lambda *_a, **_k: SimpleNamespace(user_id=1, is_shared=0),
    )
    user = SimpleNamespace(id=1, is_admin=False)

    first = await chat_routes.submit_secret_input(
        "agent-1", _body(record), _request(), user=user, server=server
    )
    await _drain(first)

    with pytest.raises(OctopError) as err:
        await chat_routes.submit_secret_input(
            "agent-1", _body(record), _request(), user=user, server=server
        )
    assert err.value.code == ErrorCode.SECRET_REQUEST_INVALID
    secrets.store_slot.assert_called_once()


@pytest.mark.asyncio
async def test_shared_agent_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    hitl = HitlChannelCoordinator()
    record = _seed_pending(hitl)
    server, _secrets, _registry = _make_server(hitl)
    monkeypatch.setattr(
        chat_routes,
        "require_agent_owner_row",
        lambda *_a, **_k: SimpleNamespace(user_id=1, is_shared=1),
    )
    user = SimpleNamespace(id=1, is_admin=False)

    with pytest.raises(OctopError) as err:
        await chat_routes.submit_secret_input(
            "agent-1", _body(record), _request(), user=user, server=server
        )
    assert err.value.code == ErrorCode.FORBIDDEN


@pytest.mark.asyncio
async def test_non_secret_pending_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    hitl = HitlChannelCoordinator()
    record = hitl.store.register(
        thread_id="thr-1",
        agent_id="agent-1",
        user_id=1,
        session_key="agent-1:dashboard:1:dm",
        channel_type="dashboard",
        action_requests=[{"name": "execute", "args": {"command": "ls"}}],
        review_configs=None,
    )
    server, _secrets, _registry = _make_server(hitl)
    monkeypatch.setattr(
        chat_routes,
        "require_agent_owner_row",
        lambda *_a, **_k: SimpleNamespace(user_id=1, is_shared=0),
    )
    user = SimpleNamespace(id=1, is_admin=False)

    with pytest.raises(OctopError) as err:
        await chat_routes.submit_secret_input(
            "agent-1", _body(record), _request(), user=user, server=server
        )
    assert err.value.code == ErrorCode.SECRET_REQUEST_INVALID


@pytest.mark.asyncio
async def test_store_failure_reopens_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    hitl = HitlChannelCoordinator()
    record = _seed_pending(hitl)
    server, secrets, _registry = _make_server(hitl)
    secrets.store_slot.side_effect = OctopError(ErrorCode.SECRET_WRITE_FAILED, "disk full")
    monkeypatch.setattr(
        chat_routes,
        "require_agent_owner_row",
        lambda *_a, **_k: SimpleNamespace(user_id=1, is_shared=0),
    )
    user = SimpleNamespace(id=1, is_admin=False)

    with pytest.raises(OctopError):
        await chat_routes.submit_secret_input(
            "agent-1", _body(record), _request(), user=user, server=server
        )
    assert hitl.store.get(record.pending_id).status == "pending"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_generic_resume_rejects_secret_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    hitl = HitlChannelCoordinator()
    record = _seed_pending(hitl)
    server, _secrets, _registry = _make_server(hitl)
    monkeypatch.setattr(chat_routes, "assert_agent_access", lambda *_a, **_k: None)
    from octop.api.routers.chat.models import HitlResumeBody

    body = HitlResumeBody(
        thread_id="thr-1",
        decisions=[{"type": "respond", "message": _SECRET_MARKER}],
        pending_id=record.pending_id,
    )
    user = SimpleNamespace(id=1, is_admin=False)

    with pytest.raises(OctopError) as err:
        await chat_routes.resume_hitl("agent-1", body, _request(), user=user, server=server)
    assert err.value.code == ErrorCode.SECRET_REQUEST_INVALID


# ---------------------------------------------------- 422 validation echo


def _build_echo_app() -> FastAPI:
    from octop.api.app import _install_exception_handlers

    app = FastAPI()
    _install_exception_handlers(app)

    def _raise() -> None:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "value"),
                    "msg": "Invalid input",
                    "input": _SECRET_MARKER,
                    "ctx": {"error": _SECRET_MARKER},
                }
            ]
        )

    @app.post("/api/agents/{agent_id}/chat/secret-input/submit")
    async def secret_route(agent_id: str) -> None:
        _raise()

    @app.post("/api/agents/{agent_id}/chat/other/submit")
    async def lookalike_route(agent_id: str) -> None:
        _raise()

    return app


def test_validation_422_does_not_echo_secret_on_submit_route() -> None:
    client = TestClient(_build_echo_app())
    r = client.post("/api/agents/a1/chat/secret-input/submit", json={})
    assert r.status_code == 422
    assert _SECRET_MARKER not in r.text
    assert r.json()["detail"][0]["loc"] == ["body", "value"]


def test_validation_422_keeps_stock_body_on_lookalike_route() -> None:
    client = TestClient(_build_echo_app())
    r = client.post("/api/agents/a1/chat/other/submit", json={})
    assert r.status_code == 422
    assert _SECRET_MARKER in r.text
