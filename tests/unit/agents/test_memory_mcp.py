"""Unit tests for the expert memory MCP server (infra/agents/memory_mcp)."""

from __future__ import annotations

from unittest import mock

import pytest

from octop.infra.agents import memory_mcp as mm


@pytest.fixture
def fake_memory(monkeypatch):
    mem = mock.MagicMock()
    mem.recall.return_value = []
    node = mock.MagicMock()
    node.id = "node1"
    node.content = "remember X"
    mem.store.return_value = node
    mem.add_raw.return_value = mock.MagicMock(id="evt1")
    mem.deprecate_atom.return_value = True
    monkeypatch.setattr(mm, "_open_memory", lambda server, agent_id: mem)
    return mem


def _tools(mcp):
    return mcp._tool_manager._tools


def test_build_binds_agent_id(monkeypatch):
    """Tools capture agent_id in the closure; callers never pass it."""
    captured = {}

    def fake_open(server, agent_id):
        captured["agent_id"] = agent_id
        mem = mock.MagicMock()
        mem.store.return_value = mock.MagicMock(id="n1", content="x")
        return mem

    monkeypatch.setattr(mm, "_open_memory", fake_open)
    mcp = mm.build_memory_mcp(mock.MagicMock(), agent_id="EXPERT42")
    _tools(mcp)["memory_save"].fn(content="x", source="s")
    assert captured["agent_id"] == "EXPERT42"


def test_build_registers_five_tools(fake_memory):
    mcp = mm.build_memory_mcp(mock.MagicMock(), "A1")
    assert set(_tools(mcp)) == {
        "memory_recall",
        "memory_save",
        "memory_capture",
        "memory_update",
        "memory_search_raw",
    }


def test_memory_recall_uses_full_pipeline(fake_memory, monkeypatch):
    """memory_recall runs the full recall pipeline (recall_for_prompt)."""
    import harness_memory.pipeline.recall as _recall

    class _Snippet:
        source_id = "atom-1"
        timestamp_iso = "2026-08-19T00:00:00+00:00"
        layer = "atom"
        text = "billing-migration is the local clone"

    fake_result = mock.MagicMock()
    fake_result.snippets = [_Snippet()]
    fake_result.rendered = "markdown"
    monkeypatch.setattr(_recall, "recall_for_prompt", lambda m, q, limit: fake_result)

    mcp = mm.build_memory_mcp(mock.MagicMock(), "A1")
    result = _tools(mcp)["memory_recall"].fn(query="billing-migration", limit=3)
    assert result["count"] == 1
    assert result["memories"][0]["text"] == "billing-migration is the local clone"
    assert result["rendered"] == "markdown"


def test_memory_save_goes_store(fake_memory):
    mcp = mm.build_memory_mcp(mock.MagicMock(), "A1")
    result = _tools(mcp)["memory_save"].fn(content="remember X", source="coding-agent")
    kwargs = fake_memory.store.call_args.kwargs
    assert kwargs["topic"] is None
    assert kwargs["metadata"] == {"source": "coding-agent"}
    assert result["source"] == "coding-agent"


def test_memory_capture_goes_add_raw(fake_memory):
    mcp = mm.build_memory_mcp(mock.MagicMock(), "A1")
    result = _tools(mcp)["memory_capture"].fn(
        content="raw conversation", source="review-bot", session_id="review-1"
    )
    kwargs = fake_memory.add_raw.call_args.kwargs
    assert kwargs["event_type"] == "manual"
    assert kwargs["host"] == "mcp-external"
    assert kwargs["session_id"] == "review-1"
    assert kwargs["payload"] == {"source": "review-bot"}
    assert result["recorded"] is True
    assert "raw (L0)" in result["note"]


def test_memory_search_raw_queries_l0(fake_memory):
    class _Evt:
        id = "evt1"
        timestamp = __import__("datetime").datetime(2026, 8, 19)
        session_id = "review-1"
        user = "u1"
        payload = {"source": "review-bot"}
        content = "report panel banner hidden"

    fake_memory.search_raw.return_value = [_Evt()]
    mcp = mm.build_memory_mcp(mock.MagicMock(), "A1")
    result = _tools(mcp)["memory_search_raw"].fn(query="report panel banner", limit=5)
    fake_memory.search_raw.assert_called_once_with("report panel banner", limit=5)
    assert result["count"] == 1
    assert result["events"][0]["event_id"] == "evt1"
    assert result["events"][0]["source"] == "review-bot"


def test_memory_update_deprecates_and_saves(fake_memory):
    mcp = mm.build_memory_mcp(mock.MagicMock(), "A1")
    result = _tools(mcp)["memory_update"].fn(
        atom_id="atom1", new_content="new fact", source="review-bot"
    )
    fake_memory.deprecate_atom.assert_called_once_with("atom1", actor="user", note="mcp update")
    assert fake_memory.store.call_args.kwargs["metadata"] == {
        "source": "review-bot",
        "supersedes": "atom1",
    }
    assert result["deprecated"] is True


def _asgi_scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict:
    return {"type": "http", "headers": headers or []}


@pytest.mark.asyncio
async def test_token_middleware_rejects_bad_token():
    inner_called = False

    async def _inner(scope, receive, send):
        nonlocal inner_called
        inner_called = True

    mw = mm._TokenAuthMiddleware(_inner, "secret")
    sent = []
    scope = _asgi_scope([(b"authorization", b"Bearer wrong")])

    async def _send(msg):
        sent.append(msg)

    await mw(scope, lambda: {}, _send)
    assert inner_called is False
    assert sent[0]["status"] == 401


@pytest.mark.asyncio
async def test_token_middleware_accepts_bearer():
    inner_called = False

    async def _inner(scope, receive, send):
        nonlocal inner_called
        inner_called = True

    mw = mm._TokenAuthMiddleware(_inner, "secret")
    scope = _asgi_scope([(b"authorization", b"Bearer secret")])
    await mw(scope, lambda: {}, lambda msg: None)
    assert inner_called is True


def test_mount_fail_closed_without_token(monkeypatch):
    monkeypatch.delenv("OCTOP_MEMORY_MCP_TOKEN", raising=False)
    app = mock.MagicMock()
    assert mm.mount_memory_mcp(app, mock.MagicMock()) == []
    app.mount.assert_not_called()


def test_mount_unified_path_with_header_router(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("OCTOP_MEMORY_MCP_TOKEN", "secret")
    app = mock.MagicMock()
    server = SimpleNamespace(
        services=SimpleNamespace(
            agent_repo=mock.MagicMock(
                list_all=lambda include_disabled: [
                    SimpleNamespace(agent_id="A1"),
                    SimpleNamespace(agent_id="A2"),
                ]
            )
        )
    )
    managers = mm.mount_memory_mcp(app, server)
    assert len(managers) == 2
    # unified path mounted exactly once
    app.mount.assert_called_once()
    assert app.mount.call_args.args[0] == "/mcp/memory"


@pytest.mark.asyncio
async def test_agent_router_routes_by_header():
    """_AgentRouter routes to the right app by X-Octop-Agent-Id header."""
    called = {}

    class _FakeApp:
        def __init__(self, aid):
            self._aid = aid

        async def __call__(self, scope, receive, send):
            called["agent"] = self._aid

    router = mm._AgentRouter({"A1": _FakeApp("A1"), "A2": _FakeApp("A2")})
    scope = {"type": "http", "headers": [(b"x-octop-agent-id", b"A2")]}
    await router(scope, lambda: {}, lambda msg: None)
    assert called["agent"] == "A2"


@pytest.mark.asyncio
async def test_agent_router_404_unknown_agent():
    """Unknown agent_id returns 404."""
    router = mm._AgentRouter({"A1": mock.MagicMock()})
    scope = {"type": "http", "headers": [(b"x-octop-agent-id", b"NOPE")]}
    sent = []

    async def _send(msg):
        sent.append(msg)

    await router(scope, lambda: {}, _send)
    assert sent[0]["status"] == 404
