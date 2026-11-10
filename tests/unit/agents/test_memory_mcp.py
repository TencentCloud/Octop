"""Unit tests for the expert memory MCP server (infra/agents/memory_mcp).

Covers the post-review surface: user-bound token auth, per-request expert access
checks, capture through ``MemoryRuntime.capture`` (redaction included), save
through ``MemoryService.save``, owner-only review tools, and the lifespan /
mount rules.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from types import SimpleNamespace
from typing import Any

import pytest

from octop.infra.agents import memory_mcp as mm

# ─── fakes ──────────────────────────────────────────────────────────────────


class _User:
    def __init__(self, user_id: int, username: str, *, is_admin: bool = False) -> None:
        self.id = user_id
        self.username = username
        self.is_admin = is_admin


class _UserManager:
    def __init__(self, users: dict[int, _User]) -> None:
        self._users = users

    def get_by_id(self, user_id: int) -> _User | None:
        return self._users.get(user_id)


class _AgentRow:
    def __init__(
        self, *, user_id: int | None, enabled: bool = True, is_shared: bool = False
    ) -> None:
        self.user_id = user_id
        self.enabled = enabled
        self.is_shared = 1 if is_shared else 0
        self.config_json = None


class _AgentRepo:
    def __init__(self, rows: dict[str, _AgentRow]) -> None:
        self._rows = rows

    def get(self, agent_id: str) -> _AgentRow | None:
        return self._rows.get(agent_id)


class _TokenRow:
    def __init__(
        self,
        *,
        token_id: str = "tok1",
        user_id: int = 1,
        name: str = "codex@macbook",
        expert_ids: list[str] | None = None,
        token_hash: str,
        revoked_at: str | None = None,
        disabled_clients: list[str] | None = None,
    ) -> None:
        self.token_id = token_id
        self.user_id = user_id
        self.name = name
        self.expert_ids = expert_ids
        self.token_hash = token_hash
        self.revoked_at = revoked_at
        self.disabled_clients = disabled_clients


class _TokenRepo:
    def __init__(self, rows: dict[str, _TokenRow] | None = None) -> None:
        self.rows = rows or {}
        self.touched: list[str] = []
        self.recorded: list[tuple[str, str]] = []

    def get_by_token_hash(self, token_hash: str) -> _TokenRow | None:
        return self.rows.get(token_hash)

    def touch(self, token_id: str) -> None:
        self.touched.append(token_id)

    def record_client(self, token_id: str, client: str) -> None:
        self.recorded.append((token_id, client))

    def any_active(self) -> bool:
        return any(row.revoked_at is None for row in self.rows.values())


def _server(
    *,
    agents: dict[str, _AgentRow] | None = None,
    users: dict[int, _User] | None = None,
    token_repo: _TokenRepo | None = None,
    app_runtime: Any = None,
) -> Any:
    repos = SimpleNamespace(
        memory_mcp_token_repo=token_repo or _TokenRepo(),
        agent_repo=_AgentRepo(agents or {"A1": _AgentRow(user_id=1)}),
    )
    services = SimpleNamespace(repos=repos, agent_repo=repos.agent_repo, config=None, paths=None)
    return SimpleNamespace(
        services=services,
        user_manager=_UserManager(users or {1: _User(1, "alice")}),
        app_runtime=app_runtime,
    )


def _tools(mcp: Any) -> dict[str, Any]:
    return mcp._tool_manager._tools


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _call_tool(mcp: Any, name: str, **kwargs: Any) -> Any:
    return _run(_tools(mcp)[name].fn(**kwargs))


@pytest.fixture
def bind_agent():
    token = mm._current_agent_id.set("A1")
    try:
        yield "A1"
    finally:
        mm._current_agent_id.reset(token)


@pytest.fixture
def bind_user():
    user_cv = mm._current_user_id.set(1)
    name_cv = mm._current_user_name.set("alice")
    try:
        yield "alice"
    finally:
        mm._current_user_name.reset(name_cv)
        mm._current_user_id.reset(user_cv)


# ─── registration ───────────────────────────────────────────────────────────


def test_build_registers_nine_tools():
    mcp = mm.build_memory_mcp(_server())
    assert set(_tools(mcp)) == {
        "memory_search",
        "memory_get",
        "memory_save",
        "memory_capture",
        "memory_raws",
        "memory_candidates",
        "memory_extract",
        "memory_promote",
        "memory_reject",
    }


def test_every_tool_is_async():
    """Blocking DB work must run off the event loop (review item 4)."""
    mcp = mm.build_memory_mcp(_server())
    for name, tool in _tools(mcp).items():
        assert inspect.iscoroutinefunction(tool.fn), name


def test_tools_run_blocking_work_off_the_event_loop(bind_agent, bind_user, monkeypatch):
    """Review test ask: a tool call must not block other requests."""
    import threading

    seen: list[int] = []

    def fake_pipeline(memory, query, max_results, *, atom_only, caller=""):
        seen.append(threading.get_ident())
        return []

    monkeypatch.setattr(mm, "_pipeline_hits", fake_pipeline)
    monkeypatch.setattr(mm, "_open_memory", lambda server, agent_id: SimpleNamespace())
    mcp = mm.build_memory_mcp(_server())

    result = _call_tool(mcp, "memory_search", query="x")

    assert result["hits"] == []
    assert seen and seen[0] != threading.get_ident()


# ─── token auth middleware ──────────────────────────────────────────────────


def _http_scope(headers: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "http",
        "method": "POST",
        "path": "/mcp/memory/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }


async def _capture_response(
    middleware: Any, scope: dict[str, Any]
) -> tuple[int, list[dict[str, Any]]]:
    status: list[int] = []
    bodies: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            status.append(int(message["status"]))
        elif message["type"] == "http.response.body":
            bodies.append(message)

    await middleware(scope, receive, send)
    return (status[0] if status else 0), bodies


async def test_middleware_rejects_missing_token():
    inner_called = False

    async def inner(scope, receive, send):
        nonlocal inner_called
        inner_called = True

    mw = mm._TokenAuthMiddleware(inner, _server())
    status, _ = await _capture_response(mw, _http_scope({}))
    assert status == 401
    assert inner_called is False


async def test_middleware_rejects_unknown_and_revoked_tokens():
    repo = _TokenRepo()
    mw = mm._TokenAuthMiddleware(lambda *a: None, _server(token_repo=repo))
    status, _ = await _capture_response(mw, _http_scope({"authorization": "Bearer omcp_unknown"}))
    assert status == 401

    token = "omcp_live"
    repo.rows[mm.hash_token(token)] = _TokenRow(
        token_hash=mm.hash_token(token), revoked_at="2026-01-01T00:00:00Z"
    )
    status, _ = await _capture_response(mw, _http_scope({"authorization": f"Bearer {token}"}))
    assert status == 401


async def test_middleware_sets_user_from_token_and_ignores_user_header():
    token = "omcp_live"
    repo = _TokenRepo()
    repo.rows[mm.hash_token(token)] = _TokenRow(token_hash=mm.hash_token(token))
    seen: dict[str, Any] = {}

    async def inner(scope, receive, send):
        seen["user_id"] = mm._current_user_id.get()
        seen["user_name"] = mm._current_user_name.get()
        seen["token_name"] = mm._current_token_name.get()

    mw = mm._TokenAuthMiddleware(inner, _server(token_repo=repo))
    status, _ = await _capture_response(
        mw,
        _http_scope(
            {
                "authorization": f"Bearer {token}",
                # a client cannot name somebody else:
                "x-octop-user-id": "bob",
            }
        ),
    )
    assert status != 401
    assert seen == {"user_id": 1, "user_name": "alice", "token_name": "codex@macbook"}
    assert repo.touched == ["tok1"]


async def test_middleware_records_identifying_client():
    token = "omcp_live"
    repo = _TokenRepo()
    repo.rows[mm.hash_token(token)] = _TokenRow(token_hash=mm.hash_token(token))
    called = False

    async def inner(scope, receive, send):
        nonlocal called
        called = True

    mw = mm._TokenAuthMiddleware(inner, _server(token_repo=repo))
    status, _ = await _capture_response(
        mw,
        _http_scope({"authorization": f"Bearer {token}", "x-octop-client": "  codex  "}),
    )
    assert status != 401 and status != 403
    assert called is True
    assert repo.recorded == [("tok1", "codex")]  # stripped before recording


async def test_middleware_truncates_long_client_names():
    token = "omcp_live"
    repo = _TokenRepo()
    repo.rows[mm.hash_token(token)] = _TokenRow(token_hash=mm.hash_token(token))

    async def inner(scope, receive, send):
        return None

    mw = mm._TokenAuthMiddleware(inner, _server(token_repo=repo))
    await _capture_response(
        mw, _http_scope({"authorization": f"Bearer {token}", "x-octop-client": "c" * 100})
    )
    assert repo.recorded == [("tok1", "c" * 64)]


async def test_middleware_blocks_disabled_client_after_recording_it():
    token = "omcp_live"
    repo = _TokenRepo()
    repo.rows[mm.hash_token(token)] = _TokenRow(
        token_hash=mm.hash_token(token), disabled_clients=["codex"]
    )
    called = False

    async def inner(scope, receive, send):
        nonlocal called
        called = True

    mw = mm._TokenAuthMiddleware(inner, _server(token_repo=repo))
    status, bodies = await _capture_response(
        mw,
        _http_scope({"authorization": f"Bearer {token}", "x-octop-client": "codex"}),
    )
    assert status == 403
    assert called is False
    assert json.loads(bodies[0]["body"]) == {
        "error": "this client is disabled for this token",
        "client": "codex",
    }
    assert repo.recorded == [("tok1", "codex")]  # counted before the refusal
    assert repo.touched == []


async def test_middleware_allows_other_clients_and_requests_without_the_header():
    token = "omcp_live"
    repo = _TokenRepo()
    repo.rows[mm.hash_token(token)] = _TokenRow(
        token_hash=mm.hash_token(token), disabled_clients=["codex"]
    )
    seen_clients: list[tuple[int, str]] = []

    async def inner(scope, receive, send):
        seen_clients.append((int(mm._current_user_id.get() or 0), mm._current_token_name.get()))

    mw = mm._TokenAuthMiddleware(inner, _server(token_repo=repo))
    allowed, _ = await _capture_response(
        mw,
        _http_scope({"authorization": f"Bearer {token}", "x-octop-client": "cursor"}),
    )
    assert allowed != 403
    # no header at all: unchanged behaviour — no stats, no block
    allowed, _ = await _capture_response(mw, _http_scope({"authorization": f"Bearer {token}"}))
    assert allowed != 403
    assert seen_clients == [(1, "codex@macbook"), (1, "codex@macbook")]
    assert repo.recorded == [("tok1", "cursor")]  # only the identifying request


async def test_middleware_survives_client_stats_failures():
    token = "omcp_live"
    repo = _TokenRepo()
    repo.rows[mm.hash_token(token)] = _TokenRow(token_hash=mm.hash_token(token))

    def boom(token_id: str, client: str) -> None:
        raise RuntimeError("stats store is down")

    repo.record_client = boom  # type: ignore[method-assign]
    called = False

    async def inner(scope, receive, send):
        nonlocal called
        called = True

    mw = mm._TokenAuthMiddleware(inner, _server(token_repo=repo))
    status, _ = await _capture_response(
        mw,
        _http_scope({"authorization": f"Bearer {token}", "x-octop-client": "codex"}),
    )
    assert status != 403
    assert called is True


# ─── expert binding + access checks ────────────────────────────────────────


async def _run_agent_router(server: Any, agent_id: str) -> tuple[int, bool]:
    called = False

    async def inner(scope, receive, send):
        nonlocal called
        called = True

    router = mm._AgentRouter(inner, server)
    status, _ = await _capture_response(
        router,
        _http_scope({"x-octop-agent-id": agent_id}),
    )
    return status, called


async def test_agent_router_rejects_unknown_and_disabled_agents():
    server = _server(agents={"A1": _AgentRow(user_id=1, enabled=False)})
    user_cv = mm._current_user_id.set(1)
    try:
        status, called = await _run_agent_router(server, "missing")
        assert status == 404 and called is False
        status, called = await _run_agent_router(server, "A1")
        assert status == 404 and called is False
    finally:
        mm._current_user_id.reset(user_cv)


async def test_agent_router_enforces_token_scope():
    server = _server(agents={"A1": _AgentRow(user_id=1), "A2": _AgentRow(user_id=1)})
    user_cv = mm._current_user_id.set(1)
    scope_cv = mm._current_token_scope.set(["A2"])
    try:
        status, called = await _run_agent_router(server, "A1")
        assert status == 403 and called is False
        status, called = await _run_agent_router(server, "A2")
        assert called is True
    finally:
        mm._current_token_scope.reset(scope_cv)
        mm._current_user_id.reset(user_cv)


async def test_agent_router_rejects_other_users_expert():
    server = _server(agents={"A1": _AgentRow(user_id=2)})
    user_cv = mm._current_user_id.set(1)
    try:
        status, called = await _run_agent_router(server, "A1")
        assert status == 403 and called is False
    finally:
        mm._current_user_id.reset(user_cv)


async def test_agent_router_allows_shared_expert(monkeypatch):
    server = _server(agents={"A1": _AgentRow(user_id=2, is_shared=True)})
    monkeypatch.setattr(
        "octop.infra.users.groups.expert_visible_to", lambda *a, **k: True, raising=False
    )
    user_cv = mm._current_user_id.set(1)
    try:
        status, called = await _run_agent_router(server, "A1")
        assert called is True
    finally:
        mm._current_user_id.reset(user_cv)


_NO_AGENT_HEADER_HINT = "either bind the token to a single expert, or send X-Octop-Agent-Id"


async def _run_agent_router_without_header(server: Any) -> tuple[int, dict[str, Any], bool]:
    """Run the router with no ``X-Octop-Agent-Id``: (status, error body, called)."""
    called = False

    async def inner(scope, receive, send):
        nonlocal called
        called = True

    router = mm._AgentRouter(inner, server)
    status, bodies = await _capture_response(router, _http_scope({}))
    body = json.loads(b"".join(part.get("body", b"") for part in bodies) or b"{}")
    return status, body, called


async def test_single_expert_token_routes_capture_without_agent_header(monkeypatch):
    """唯一令牌：token 绑定一个专家时，客户端不带 X-Octop-Agent-Id 也能 capture。"""
    server = _server(agents={"A1": _AgentRow(user_id=1)})
    runtime = _FakeRuntime()
    scheduled: list[tuple[str, str]] = []
    monkeypatch.setattr(mm, "_memory_runtime", lambda server, agent_id: runtime)
    monkeypatch.setattr(
        mm,
        "_schedule_extract",
        lambda server, agent_id, session_id, *, promote: (
            scheduled.append((agent_id, session_id)) or False
        ),
    )
    mcp = mm.build_memory_mcp(server)
    seen: dict[str, Any] = {}

    async def inner(scope, receive, send):
        seen["agent_id"] = mm._current_agent_id.get()
        await _tools(mcp)["memory_capture"].fn(content="唯一令牌", source="codex", session_id="s1")

    user_cv = mm._current_user_id.set(1)
    scope_cv = mm._current_token_scope.set(["A1"])
    try:
        status, bodies = await _capture_response(mm._AgentRouter(inner, server), _http_scope({}))
    finally:
        mm._current_token_scope.reset(scope_cv)
        mm._current_user_id.reset(user_cv)

    assert status == 0 and bodies == []
    assert seen["agent_id"] == "A1"
    assert len(runtime.calls) == 1
    assert scheduled == [("A1", "s1")]


async def test_multi_expert_token_without_agent_header_is_a_400():
    server = _server(agents={"A1": _AgentRow(user_id=1), "A2": _AgentRow(user_id=1)})
    user_cv = mm._current_user_id.set(1)
    scope_cv = mm._current_token_scope.set(["A1", "A2"])
    try:
        status, body, called = await _run_agent_router_without_header(server)
    finally:
        mm._current_token_scope.reset(scope_cv)
        mm._current_user_id.reset(user_cv)

    assert status == 400 and called is False
    assert body["error"] == _NO_AGENT_HEADER_HINT
    assert body["allowed_expert_ids"] == ["A1", "A2"]


async def test_unrestricted_token_without_agent_header_is_a_400():
    server = _server(agents={"A1": _AgentRow(user_id=1)})
    user_cv = mm._current_user_id.set(1)
    scope_cv = mm._current_token_scope.set(None)
    try:
        status, body, called = await _run_agent_router_without_header(server)
    finally:
        mm._current_token_scope.reset(scope_cv)
        mm._current_user_id.reset(user_cv)

    assert status == 400 and called is False
    assert body["error"] == _NO_AGENT_HEADER_HINT
    assert "allowed_expert_ids" not in body


async def test_single_expert_token_still_checks_expert_access():
    """回退到唯一专家时，存在性 / 启用 / owner 可见性仍按原规则校验。"""
    disabled = _server(agents={"A1": _AgentRow(user_id=1, enabled=False)})
    foreign = _server(agents={"A1": _AgentRow(user_id=2)})
    user_cv = mm._current_user_id.set(1)
    scope_cv = mm._current_token_scope.set(["A1"])
    try:
        status, _, called = await _run_agent_router_without_header(disabled)
        assert status == 404 and called is False
        status, _, called = await _run_agent_router_without_header(foreign)
        assert status == 403 and called is False
    finally:
        mm._current_token_scope.reset(scope_cv)
        mm._current_user_id.reset(user_cv)


# ─── capture: runtime application layer + redaction ────────────────────────


class _FakeRuntime:
    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._result = result or {"accepted": 1}

    def capture(self, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(params)
        return self._result


def test_capture_goes_through_runtime_with_metadata(bind_agent, bind_user, monkeypatch):
    runtime = _FakeRuntime()
    monkeypatch.setattr(mm, "_memory_runtime", lambda server, agent_id: runtime)
    scheduled: list[tuple[str, str, bool]] = []
    monkeypatch.setattr(
        mm,
        "_schedule_extract",
        lambda server, agent_id, session_id, *, promote: (
            scheduled.append((agent_id, session_id, promote)) or True
        ),
    )
    mcp = mm.build_memory_mcp(_server())

    result = _call_tool(
        mcp,
        "memory_capture",
        content="把 MCP 写入路径补齐",
        assistant="决定改走 runtime.capture",
        source="claude-code",
        session_id="s1",
    )

    assert result["recorded"] is True
    params = runtime.calls[0]
    assert params["host"] == "claude-code"
    assert params["session_id"] == "s1"
    assert params["user"] == "alice"
    events = params["events"]
    assert [e["event_type"] for e in events] == ["user_message", "assistant_message"]
    # caller goes into metadata, never into the body (review item 9):
    assert "alice" not in events[0]["content"]
    assert events[0]["payload"] == {
        "source": "claude-code",
        "source_host": "claude-code",
        "caller": "alice",
    }
    assert scheduled == [("A1", "s1", False)]


def test_capture_dry_run_writes_nothing(bind_agent, bind_user, monkeypatch):
    runtime = _FakeRuntime()
    monkeypatch.setattr(mm, "_memory_runtime", lambda server, agent_id: runtime)
    mcp = mm.build_memory_mcp(_server())
    result = _call_tool(mcp, "memory_capture", content="x", source="codex", dry_run=True)
    assert result["dry_run"] is True
    assert result["recorded"] is False
    assert runtime.calls == []


def test_capture_redacts_secrets_end_to_end(bind_agent, bind_user, monkeypatch, tmp_path):
    """Review test ask: secrets in captured content must be filtered."""
    from octop_memory.application.runtime import MemoryRuntime
    from octop_memory.core import Memory

    memory = Memory(
        namespace="mcp-test",
        backend="sqlite",
        backend_config={"db_path": str(tmp_path / "memory.sqlite")},
    )
    runtime = MemoryRuntime(memory)
    monkeypatch.setattr(mm, "_memory_runtime", lambda server, agent_id: runtime)
    monkeypatch.setattr(mm, "_schedule_extract", lambda *a, **k: False)
    mcp = mm.build_memory_mcp(_server())

    secret = "sk-abcdefgh12345678"
    _call_tool(mcp, "memory_capture", content=f"用这个 key：{secret}", source="codex")

    events = list(memory.list_raw(limit=10))
    assert events, "capture should have written an L0 event"
    assert all(secret not in event.content for event in events)
    assert "[REDACTED]" in events[0].content


def test_capture_accepts_client_parsed_events(bind_agent, bind_user, monkeypatch, tmp_path):
    """Clients may parse transcripts themselves and upload typed events."""
    memory = _real_memory(tmp_path)
    monkeypatch.setattr(mm, "_open_memory", lambda server, agent_id: memory)
    monkeypatch.setattr(mm, "_schedule_extract", lambda *a, **k: False)
    mcp = mm.build_memory_mcp(_server())

    result = _call_tool(
        mcp,
        "memory_capture",
        events=[
            {
                "event_type": "user_message",
                "content": "客户端自己解析好的一轮用户发言，直接上传事件",
            },
            {
                "event_type": "assistant_message",
                "content": "客户端解析的助手回复，也按事件形式上传",
            },
        ],
        source="claude-code",
        extract=False,
    )

    assert result["accepted"] >= 1
    events = list(memory.list_raw(limit=5))
    assert {event.event_type for event in events} >= {"user_message"}


def test_capture_events_honours_dry_run(bind_agent, bind_user, monkeypatch, tmp_path):
    memory = _real_memory(tmp_path)
    monkeypatch.setattr(mm, "_open_memory", lambda server, agent_id: memory)
    mcp = mm.build_memory_mcp(_server())
    result = _call_tool(
        mcp,
        "memory_capture",
        events=[{"event_type": "user_message", "content": "只解析不写入的客户端事件"}],
        source="claude-code",
        dry_run=True,
    )
    assert result["recorded"] is False
    assert len(result["events"]) == 1
    assert not list(memory.list_raw(limit=5))


# ─── capture: provenance ─────────────────────────────────────────────────


def test_capture_uses_the_token_name_as_source_host(bind_agent, bind_user, monkeypatch, tmp_path):
    memory = _real_memory(tmp_path)
    monkeypatch.setattr(mm, "_open_memory", lambda server, agent_id: memory)
    monkeypatch.setattr(mm, "_schedule_extract", lambda *a, **k: False)
    mcp = mm.build_memory_mcp(_server())

    token_cv = mm._current_token_name.set("codex@macbook")
    try:
        _call_tool(
            mcp,
            "memory_capture",
            content="来源标记应该用 token 名字而不是客户端自报的 source",
            source="spoofed-client",
            extract=False,
        )
    finally:
        mm._current_token_name.reset(token_cv)

    events = list(memory.list_raw(limit=5))
    assert events
    assert events[-1].payload["source_host"] == "codex@macbook"
    assert events[-1].payload["source"] == "spoofed-client"


# ─── capture: terminal transcript uploads ─────────────────────────────────


def _real_memory(tmp_path):
    from octop_memory.core import Memory

    return Memory(
        namespace="mcp-transcript-test",
        backend="sqlite",
        backend_config={"db_path": str(tmp_path / "memory.sqlite")},
    )


# ─── save: MemoryService application layer ────────────────────────────────


class _FakeService:
    def __init__(self) -> None:
        self.saved: list[dict[str, Any]] = []
        self.memory = SimpleNamespace(deprecate_atom=lambda *a, **k: True)
        self._runtime = SimpleNamespace(_extraction_cfg=lambda: {"promote": True})

    def save(self, content: str, *, topic=None, metadata=None):
        self.saved.append({"content": content, "topic": topic, "metadata": metadata})
        return SimpleNamespace(id="n1", content=content)


def test_save_goes_through_memory_service(bind_agent, bind_user, monkeypatch):
    service = _FakeService()
    monkeypatch.setattr(mm, "_require_live_service", lambda server, agent_id: service)
    mcp = mm.build_memory_mcp(_server())

    result = _call_tool(mcp, "memory_save", content="项目约定：先跑 make all", source="codex")

    assert result["node_id"] == "n1"
    saved = service.saved[0]
    assert saved["content"] == "项目约定：先跑 make all"  # no `<user>说：` prefix
    assert saved["metadata"] == {
        "source": "codex",
        "source_host": "codex",
        "caller": "alice",
    }


def test_save_refuses_to_start_a_stopped_expert(bind_agent):
    mcp = mm.build_memory_mcp(_server(app_runtime=None))
    with pytest.raises(RuntimeError, match="not running"):
        _call_tool(mcp, "memory_save", content="x", source="codex")


# ─── review tools are expert-owner only ───────────────────────────────────


@pytest.mark.parametrize("tool", ["memory_raws", "memory_candidates", "memory_promote"])
def test_ops_tools_are_owner_only(bind_agent, tool):
    server = _server(agents={"A1": _AgentRow(user_id=2)})
    mcp = mm.build_memory_mcp(server)
    user_cv = mm._current_user_id.set(1)
    try:
        with pytest.raises(PermissionError):
            if tool == "memory_promote":
                _call_tool(mcp, tool, candidate_ids=["c1"])
            else:
                _call_tool(mcp, tool)
    finally:
        mm._current_user_id.reset(user_cv)


def test_ops_tools_allow_the_owner(bind_agent, bind_user, monkeypatch):
    reached = []

    def fake_open(server, agent_id):
        reached.append(agent_id)
        return SimpleNamespace(search_raw=lambda *a, **k: [])

    monkeypatch.setattr(mm, "_open_memory", fake_open)
    mcp = mm.build_memory_mcp(_server())
    _call_tool(mcp, "memory_raws", query="x")
    assert reached == ["A1"]


# ─── extract: no auto-start, promote follows the expert config ────────────


def _extract_service(calls: list[dict[str, Any]]) -> Any:
    class _Service(_FakeService):
        def extract(self, session_id, *, incremental, promote, regen_pages):
            calls.append(
                {
                    "session_id": session_id,
                    "incremental": incremental,
                    "promote": promote,
                    "regen_pages": regen_pages,
                }
            )
            return {"candidates": 2, "promotion": {"promoted": 1}}

    return _Service()


def test_extract_follows_expert_promote_config(bind_agent, bind_user, monkeypatch):
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        mm, "_require_live_service", lambda server, agent_id: _extract_service(calls)
    )
    monkeypatch.setattr(mm, "_expert_extract_promote", lambda server, agent_id: True)
    mcp = mm.build_memory_mcp(_server())
    result = _call_tool(mcp, "memory_extract", session_id="s1")
    assert result["promoted"] == 1
    assert calls[0]["promote"] is True
    assert calls[0]["incremental"] is True


def test_extract_explicit_promote_false_wins(bind_agent, bind_user, monkeypatch):
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        mm, "_require_live_service", lambda server, agent_id: _extract_service(calls)
    )
    mcp = mm.build_memory_mcp(_server())
    _call_tool(mcp, "memory_extract", session_id="s1", promote=False)
    assert calls[0]["promote"] is False


def test_expert_promote_reads_the_service_config():
    service = SimpleNamespace(_runtime=SimpleNamespace(_extraction_cfg=lambda: {"promote": True}))
    agent = SimpleNamespace(_memory_runtime=SimpleNamespace(service=service))
    registry = SimpleNamespace(get_agent=lambda agent_id: agent)
    server = _server(app_runtime=SimpleNamespace(agent_registry=registry))
    assert mm._expert_extract_promote(server, "A1") is True
    # no live service -> review queue default
    assert mm._expert_extract_promote(_server(app_runtime=None), "A1") is False


async def test_schedule_extract_never_starts_a_stopped_expert(monkeypatch):
    server = _server(app_runtime=SimpleNamespace(agent_registry=object()))
    assert mm._schedule_extract(server, "A1", "s1", promote=False) is False


# ─── mount + lifespan ─────────────────────────────────────────────────────


def test_mount_is_fail_closed(monkeypatch):
    monkeypatch.delenv("OCTOP_MEMORY_MCP_ENABLED", raising=False)
    assert mm._memory_mcp_enabled() is False
    monkeypatch.setenv("OCTOP_MEMORY_MCP_ENABLED", "1")
    assert mm._memory_mcp_enabled() is True


def test_lifespan_chain_keeps_the_previous_hooks():
    from contextlib import asynccontextmanager

    seen: list[str] = []

    @asynccontextmanager
    async def previous(app):
        seen.append("previous-enter")
        yield
        seen.append("previous-exit")

    chained = mm._chain_lifespan(previous, [])

    async def _run_lifespan() -> None:
        async with chained(None):
            seen.append("body")

    asyncio.run(_run_lifespan())
    assert seen == ["previous-enter", "body", "previous-exit"]
