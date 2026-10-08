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

    def _add_raw(content, **_kwargs):
        raw = mock.MagicMock(id="evt1")
        raw.content = content
        return raw

    mem.add_raw.side_effect = _add_raw
    mem.deprecate_atom.return_value = True
    monkeypatch.setattr(mm, "_open_memory", lambda server, agent_id: mem)
    return mem


@pytest.fixture
def bind_agent():
    """Bind the request-scoped agent contextvar (main resolves the expert per request)."""
    token = mm._current_agent_id.set("A1")
    yield "A1"
    mm._current_agent_id.reset(token)


@pytest.fixture
def bind_user():
    """Bind the ``X-Octop-User-Id`` caller contextvar (sender attribution)."""
    token = mm._current_caller_user.set("alice")
    yield "alice"
    mm._current_caller_user.reset(token)


def _tools(mcp):
    return mcp._tool_manager._tools


def test_build_resolves_agent_per_request(monkeypatch):
    """Expert is bound per request (contextvar), not captured at build time."""
    captured = {}

    def fake_open(server, agent_id):
        captured["agent_id"] = agent_id
        mem = mock.MagicMock()
        mem.store.return_value = mock.MagicMock(id="n1", content="x")
        return mem

    monkeypatch.setattr(mm, "_open_memory", fake_open)
    mcp = mm.build_memory_mcp(mock.MagicMock())
    token = mm._current_agent_id.set("EXPERT42")
    try:
        _tools(mcp)["memory_save"].fn(content="x", source="s")
    finally:
        mm._current_agent_id.reset(token)
    assert captured["agent_id"] == "EXPERT42"


def test_build_registers_eleven_tools(fake_memory):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    assert set(_tools(mcp)) == {
        "memory_recall",
        "memory_search",
        "memory_get",
        "memory_save",
        "memory_capture",
        "memory_update",
        "memory_raws",
        "memory_candidates",
        "memory_extract",
        "memory_promote",
        "memory_reject",
    }


def test_memory_recall_uses_full_pipeline(fake_memory, monkeypatch, bind_agent):
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
    monkeypatch.setattr(_recall, "recall_for_prompt", lambda m, q, **kw: fake_result)

    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_recall"].fn(query="billing-migration", limit=3)
    assert result["count"] == 1
    assert result["memories"][0]["text"] == "billing-migration is the local clone"
    assert result["rendered"] == "markdown"


def test_memory_recall_forwards_session_and_thread(fake_memory, monkeypatch, bind_agent):
    """Hook callers can scope recall to a session/thread (echo guard + co-reference)."""
    import harness_memory.pipeline.recall as _recall

    captured = {}

    def _fake(memory, query, **kwargs):
        captured["memory"] = memory
        captured["query"] = query
        captured.update(kwargs)
        result = mock.MagicMock()
        result.snippets = []
        result.rendered = ""
        return result

    monkeypatch.setattr(_recall, "recall_for_prompt", _fake)
    mcp = mm.build_memory_mcp(mock.MagicMock())
    _tools(mcp)["memory_recall"].fn(
        query="那个项目",
        limit=4,
        session_id="sess-1",
        thread_id="thr-1",
    )
    assert captured["memory"] is fake_memory
    assert captured["query"] == "那个项目"
    assert captured["session_id"] == "sess-1"
    assert captured["thread_id"] == "thr-1"
    assert captured["limit"] == 4


def test_memory_recall_without_scope_passes_none(fake_memory, monkeypatch, bind_agent):
    import harness_memory.pipeline.recall as _recall

    captured = {}

    def _fake(memory, query, **kwargs):
        captured.update(kwargs)
        result = mock.MagicMock()
        result.snippets = []
        result.rendered = ""
        return result

    monkeypatch.setattr(_recall, "recall_for_prompt", _fake)
    mcp = mm.build_memory_mcp(mock.MagicMock())
    _tools(mcp)["memory_recall"].fn(query="q")
    assert captured["session_id"] is None
    assert captured["thread_id"] is None


def test_memory_save_goes_store(fake_memory, bind_agent):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_save"].fn(content="remember X", source="coding-agent")
    kwargs = fake_memory.store.call_args.kwargs
    assert kwargs["topic"] is None
    assert kwargs["metadata"] == {"source": "coding-agent"}
    assert result["source"] == "coding-agent"


def test_memory_capture_goes_add_raw(fake_memory, bind_agent):
    mcp = mm.build_memory_mcp(mock.MagicMock())
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


def test_memory_capture_is_idempotent(fake_memory, bind_agent):
    """Re-capturing the same session + content reuses the existing L0 event."""
    existing = mock.MagicMock(id="evt-existing")
    existing.content = "raw conversation"
    fake_memory.list_raw.return_value = [existing]

    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_capture"].fn(
        content="raw conversation", source="review-bot", session_id="review-1"
    )

    fake_memory.add_raw.assert_not_called()
    assert result["event_id"] == "evt-existing"
    assert result["duplicate"] is True
    assert "idempotent capture" in result["note"]


def test_memory_raws_queries_l0_with_query(fake_memory, bind_agent):
    class _Evt:
        id = "evt1"
        timestamp = __import__("datetime").datetime(2026, 8, 19)
        session_id = "review-1"
        user = "u1"
        event_type = "manual"
        payload = {"source": "review-bot"}
        content = "report panel banner hidden"

    fake_memory.search_raw.return_value = [_Evt()]
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_raws"].fn(query="report panel banner", limit=5)
    fake_memory.search_raw.assert_called_once_with("report panel banner", limit=5)
    assert result["count"] == 1
    assert result["events"][0]["event_id"] == "evt1"
    assert result["events"][0]["source"] == "review-bot"


def test_memory_update_deprecates_and_saves(fake_memory, bind_agent):
    mcp = mm.build_memory_mcp(mock.MagicMock())
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


def test_mount_unified_path_with_shared_app(monkeypatch):
    """A single shared MCP app is mounted once at /mcp/memory."""
    from types import SimpleNamespace

    monkeypatch.setenv("OCTOP_MEMORY_MCP_TOKEN", "secret")
    app = mock.MagicMock()
    server = SimpleNamespace(services=SimpleNamespace(agent_repo=mock.MagicMock()))
    managers = mm.mount_memory_mcp(app, server)
    assert len(managers) == 1
    app.mount.assert_called_once()
    assert app.mount.call_args.args[0] == "/mcp/memory"


@pytest.mark.asyncio
async def test_agent_router_routes_by_header():
    """_AgentRouter validates the agent, binds the contextvar, forwards to the shared app."""
    from types import SimpleNamespace

    seen = {}

    class _FakeApp:
        async def __call__(self, scope, receive, send):
            seen["agent"] = mm._current_agent_id.get()

    rows = {
        "A1": SimpleNamespace(agent_id="A1", enabled=True),
        "A2": SimpleNamespace(agent_id="A2", enabled=True),
    }
    server = SimpleNamespace(
        services=SimpleNamespace(agent_repo=mock.MagicMock(get=lambda aid: rows.get(aid)))
    )
    router = mm._AgentRouter(_FakeApp(), server)
    scope = {"type": "http", "headers": [(b"x-octop-agent-id", b"A2")]}
    await router(scope, lambda: {}, lambda msg: None)
    assert seen["agent"] == "A2"


@pytest.mark.asyncio
async def test_agent_router_404_unknown_agent():
    """Unknown agent_id returns 404 before dispatching."""
    from types import SimpleNamespace

    server = SimpleNamespace(
        services=SimpleNamespace(agent_repo=mock.MagicMock(get=lambda aid: None))
    )
    router = mm._AgentRouter(mock.MagicMock(), server)
    scope = {"type": "http", "headers": [(b"x-octop-agent-id", b"NOPE")]}
    sent = []

    async def _send(msg):
        sent.append(msg)

    await router(scope, lambda: {}, _send)
    assert sent[0]["status"] == 404


def test_trigger_extract_no_session_returns_false():
    """No session_id -> no extraction trigger."""
    assert mm._trigger_extract(mock.MagicMock(), None) is False


def test_trigger_extract_no_service_returns_false():
    """Agent without memory runtime/service -> silently skipped."""
    agent = mock.MagicMock()
    runtime = mock.MagicMock()
    runtime.service = None
    agent._memory_runtime = runtime
    registry = mock.MagicMock(get_agent=lambda aid: agent)
    server = mock.MagicMock()
    server.app_runtime.agent_registry = registry
    token = mm._current_agent_id.set("A1")
    try:
        assert mm._trigger_extract(server, "kiro-chat") is False
    finally:
        mm._current_agent_id.reset(token)


def test_trigger_extract_schedules_service(monkeypatch):
    """With a service, asynchronously schedule extract and return True."""
    import asyncio
    import time

    agent = mock.MagicMock()
    service = mock.MagicMock()
    runtime = mock.MagicMock()
    runtime.service = service
    agent._memory_runtime = runtime
    registry = mock.MagicMock(get_agent=lambda aid: agent)
    server = mock.MagicMock()
    server.app_runtime.agent_registry = registry

    async def _run():
        return mm._trigger_extract(server, "kiro-chat")

    token = mm._current_agent_id.set("A1")
    try:
        assert asyncio.run(_run()) is True
    finally:
        mm._current_agent_id.reset(token)
    time.sleep(0.1)
    service.extract.assert_called()
    assert service.extract.call_args.args[0] == "kiro-chat"


def _with_agent(agent_id: str):
    """Bind the request-scoped agent contextvar for a single tool call."""
    return mm._current_agent_id.set(agent_id)


def test_memory_candidates_passes_status_string(fake_memory):
    """``status`` is a typing.Literal of strings: pass the raw value, don't
    instantiate it (previously crashed with "Cannot instantiate typing.Literal")."""
    fake_memory.list_candidates.return_value = []
    mcp = mm.build_memory_mcp(mock.MagicMock())
    token = _with_agent("A1")
    try:
        result = _tools(mcp)["memory_candidates"].fn(status="pending", limit=5)
    finally:
        mm._current_agent_id.reset(token)
    assert result["candidates"] == []
    assert fake_memory.list_candidates.call_args.kwargs["status"] == "pending"


def test_memory_candidates_not_a_status_raises(fake_memory):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    token = _with_agent("A1")
    try:
        with pytest.raises(ValueError):
            _tools(mcp)["memory_candidates"].fn(status="no-such-status")
    finally:
        mm._current_agent_id.reset(token)


def test_memory_reject_passes_literal_status(fake_memory):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    token = _with_agent("A1")
    try:
        result = _tools(mcp)["memory_reject"].fn(candidate_id="c1", reason="dup")
    finally:
        mm._current_agent_id.reset(token)
    assert result["status"] == "rejected"
    assert fake_memory.update_candidate_status.call_args.kwargs["status"] == "rejected"


def _stub_runtime(monkeypatch, *, hits=None, get_result=None, captured=None):
    """Patch ``MemoryRuntime`` so search/get run against a fake runtime."""

    class _FakeRuntime:
        def __init__(self, memory):
            if captured is not None:
                captured["memory"] = memory

        def memory_search(self, params):
            if captured is not None:
                captured["search_params"] = params
            return {"hits": list(hits or []), "total": len(hits or []), "empty_reason": None}

        def memory_get(self, params):
            if captured is not None:
                captured["get_params"] = params
            return dict(get_result or {})

    import harness_memory.application.runtime as _runtime

    monkeypatch.setattr(_runtime, "MemoryRuntime", _FakeRuntime)


def test_memory_search_projects_hit_paths(fake_memory, monkeypatch, bind_agent):
    """memory_search runs the shared pipeline and returns path-carrying hits."""
    captured = {}
    _stub_runtime(
        monkeypatch,
        hits=[
            {"path": "atom/a1.md", "layer": "atom", "snippet": "s1", "source_id": "a1"},
            {"path": "raw/2026-08-19/r1.md", "layer": "raw", "snippet": "s2", "source_id": "r1"},
        ],
        captured=captured,
    )
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_search"].fn(query="billing", max_results=5)
    assert captured["memory"] is fake_memory
    assert captured["search_params"] == {"query": "billing", "maxResults": 5, "corpus": "memory"}
    assert [hit["path"] for hit in result["hits"]] == ["atom/a1.md", "raw/2026-08-19/r1.md"]
    assert result["total"] == 2
    assert result["corpus"] == "all"


def test_memory_search_atom_corpus_widens_then_filters(fake_memory, monkeypatch, bind_agent):
    """``corpus=atom`` asks for a wider pool, then keeps only L2 atoms."""
    captured = {}
    _stub_runtime(
        monkeypatch,
        hits=[
            {"path": "raw/2026-08-19/r1.md", "layer": "raw", "snippet": "s2", "source_id": "r1"},
            {"path": "atom/a1.md", "layer": "atom", "snippet": "s1", "source_id": "a1"},
            {"path": "atom/a2.md", "layer": "atom", "snippet": "s3", "source_id": "a2"},
        ],
        captured=captured,
    )
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_search"].fn(query="billing", max_results=2, corpus="atom")
    assert captured["search_params"]["maxResults"] == 8
    assert [hit["path"] for hit in result["hits"]] == ["atom/a1.md", "atom/a2.md"]
    assert result["corpus"] == "atom"


def test_memory_search_raw_corpus_uses_l0_fts(fake_memory, bind_agent):
    """``corpus=raw`` bypasses the atom-first fallback and searches L0 directly."""
    from datetime import datetime

    event = mock.MagicMock()
    event.id = "r1"
    event.content = "nginx 需要 proxy /api/memory-mcp"
    event.timestamp = datetime(2026, 8, 19, 12, 0)
    fake_memory.search_raw.return_value = [event]

    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_search"].fn(query="proxy", max_results=3, corpus="raw")
    fake_memory.search_raw.assert_called_once_with("proxy", limit=3)
    assert result["hits"][0]["path"] == "raw/2026-08-19/r1.md"
    assert result["hits"][0]["layer"] == "raw"


def test_memory_search_rejects_unknown_corpus(fake_memory, bind_agent):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    with pytest.raises(ValueError):
        _tools(mcp)["memory_search"].fn(query="billing", corpus="wiki")


def test_memory_get_returns_excerpt_as_content(fake_memory, monkeypatch, bind_agent):
    """memory_get surfaces the excerpt under ``content`` and forwards paging."""
    captured = {}
    _stub_runtime(
        monkeypatch,
        get_result={
            "path": "atom/a1.md",
            "kind": "atom",
            "excerpt": "# body",
            "metadata": {"id": "a1"},
            "total_lines": 3,
            "from_line": 1,
            "to_line": 3,
            "truncated": False,
        },
        captured=captured,
    )
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_get"].fn(path="atom/a1.md", start=1, lines=10)
    assert captured["get_params"] == {"path": "atom/a1.md", "from": 1, "lines": 10}
    assert result["content"] == "# body"
    assert result["kind"] == "atom"
    assert result["total_lines"] == 3


def test_memory_get_returns_hint_for_bad_path(fake_memory, monkeypatch, bind_agent):
    """A stale/mistyped path degrades to an error payload instead of raising."""

    class _Boom:
        def __init__(self, memory):
            pass

        def memory_get(self, params):
            raise ValueError("path must be non-empty and unpadded: 'nope'")

    import harness_memory.application.runtime as _runtime

    monkeypatch.setattr(_runtime, "MemoryRuntime", _Boom)
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_get"].fn(path="nope")
    assert "path must be non-empty" in result["error"]
    assert "atom/<atom_id>.md" in result["hint"]


def test_memory_capture_prefixes_sender(fake_memory, bind_agent, bind_user):
    """The header user id is folded into the captured text, not just the payload."""
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_capture"].fn(content="接口先不要动", source="review-bot")
    assert fake_memory.add_raw.call_args.args[0] == "alice说：接口先不要动"
    assert fake_memory.add_raw.call_args.kwargs["user"] == "alice"
    assert result["content"] == "alice说：接口先不要动"
    assert result["user"] == "alice"


def test_memory_capture_does_not_double_prefix(fake_memory, bind_agent, bind_user):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    _tools(mcp)["memory_capture"].fn(content="alice说：接口先不要动", source="review-bot")
    assert fake_memory.add_raw.call_args.args[0] == "alice说：接口先不要动"


def test_memory_save_prefixes_sender(fake_memory, bind_agent, bind_user):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    _tools(mcp)["memory_save"].fn(content="部署约定：端点挂在 /mcp/memory", source="coding-agent")
    assert fake_memory.store.call_args.args[0] == "alice说：部署约定：端点挂在 /mcp/memory"
    assert fake_memory.store.call_args.kwargs["metadata"]["user"] == "alice"


def test_memory_update_prefixes_sender(fake_memory, bind_agent, bind_user):
    mcp = mm.build_memory_mcp(mock.MagicMock())
    _tools(mcp)["memory_update"].fn(
        atom_id="a1", new_content="端点改到 /api/memory-mcp", source="s"
    )
    assert fake_memory.store.call_args.args[0] == "alice说：端点改到 /api/memory-mcp"


def test_write_without_caller_keeps_content(fake_memory, bind_agent):
    """No ``X-Octop-User-Id`` -> no attribution prefix."""
    mcp = mm.build_memory_mcp(mock.MagicMock())
    _tools(mcp)["memory_save"].fn(content="no sender", source="coding-agent")
    assert fake_memory.store.call_args.args[0] == "no sender"


@pytest.mark.parametrize(
    "content",
    [
        "[memory] Earlier in this workspace, related to your question:\n- [atom] x",
        "结论见下：\n## Memory Recall\n- [atom] y\n[/memory]",
    ],
)
def test_memory_capture_drops_recall_echo(fake_memory, bind_agent, content):
    """Injected recall blocks are not captured back (mirrors skip_memory_echo)."""
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_capture"].fn(content=content, source="hook")
    assert result["recorded"] is False
    assert result["skipped"] == "recall_echo"
    assert "recall_echo" in result["skipped"]
    fake_memory.add_raw.assert_not_called()


def test_memory_capture_still_records_normal_content(fake_memory, bind_agent, bind_user):
    """The echo guard must not block ordinary captures."""
    mcp = mm.build_memory_mcp(mock.MagicMock())
    result = _tools(mcp)["memory_capture"].fn(content="接口先不要动", source="hook")
    assert result["recorded"] is True
    assert fake_memory.add_raw.call_args.args[0] == "alice说：接口先不要动"
