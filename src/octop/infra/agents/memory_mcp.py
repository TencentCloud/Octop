"""Expose Octop expert memory as an MCP server for external agents.

External agents (coding agents, bots) read and write one expert's memory over MCP
(Streamable HTTP). The endpoint is a single ``/mcp/memory`` mount; the expert is
selected per request with ``X-Octop-Agent-Id`` and the caller is identified by a
**user-bound token** (``Authorization: Bearer omcp_…``) — never by a header the
client can choose.

Auth model (owner: Octop users, not a shared instance token):

* each user creates tokens in the dashboard / ``POST /api/memory-mcp/tokens``;
  a token can be limited to a set of experts and is revocable per client
  (``name`` is the client label, e.g. ``codex@macbook``);
* only the sha256 hash is stored, and verification is a constant-time compare;
* the caller's Octop user comes from the token, and every request re-checks
  that the user may access the selected expert (owner / shared-expert rules),
  so a token cannot be pointed at somebody else's expert by editing a header.

Tool surface (``a`` scope of the review split):

* everyday, any token: ``memory_search`` / ``memory_get`` / ``memory_save`` /
  ``memory_capture``;
* review & ops, **expert owner only**: ``memory_raws`` / ``memory_candidates`` /
  ``memory_extract`` / ``memory_promote`` / ``memory_reject`` (the dashboard has
  the same operations; exposing them to every external agent would let an agent
  promote its own writes).

Write paths go through the octop-memory application layer so behaviour matches
the in-process tools: ``memory_capture`` -> ``MemoryRuntime.capture`` (privacy
redaction, role/min-length policy, recall-echo guard) and ``memory_save`` ->
``MemoryService.save`` (manual-review scheduler). Captured writes land in the L0
raw layer and are extracted in the background; extraction **promotes only when
the expert's own extraction config asks for it** — by default external writes
wait in the review queue.

No background extraction starts a stopped expert: an idle expert has no live
``MemoryService`` (and starting it would spend the user's model budget), so the
capture is recorded and extraction is skipped until the expert runs.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from contextvars import ContextVar
from typing import Any, get_args

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from octop.infra.agents.memory.backend import open_memory_kwargs
from octop.infra.agents.memory_tokens import hash_token, token_matches
from octop.infra.server import OctopServer

logger = logging.getLogger(__name__)

# 当前 MCP HTTP 请求的绑定状态（由 _TokenAuthMiddleware / _AgentRouter 写入，
# 工具读取）。stateless streamable HTTP 下 mcp SDK 不提供 ctx.request_context，
# 故用 contextvar 在 ASGI 中间件与工具之间传递。
_current_agent_id: ContextVar[str] = ContextVar("octop_mcp_agent_id", default="")
_current_user_id: ContextVar[int | None] = ContextVar("octop_mcp_user_id", default=None)
_current_user_name: ContextVar[str] = ContextVar("octop_mcp_user_name", default="")
_current_token_name: ContextVar[str] = ContextVar("octop_mcp_token_name", default="")
_current_token_scope: ContextVar[list[str] | None] = ContextVar(
    "octop_mcp_token_scope", default=None
)
"""Experts a token is limited to, or ``None`` when unrestricted."""

_SEARCH_CORPORA: frozenset[str] = frozenset({"all", "memory", "atom", "raw"})
"""Corpora ``memory_search`` accepts. ``atom``/``raw`` are layer filters over the
recall pipeline; ``all``/``memory`` are the same pipeline without a filter."""

_SNIPPET_CHARS = 200

_USER_ROLE = "user_message"
_ASSISTANT_ROLE = "assistant_message"

_EXTRACT_TASKS: set[asyncio.Task[None]] = set()
"""Strong references to background extraction tasks (``asyncio`` only keeps a weak
one, so an unreferenced task may be garbage-collected mid-flight)."""

_EXTRACT_LOCKS: dict[str, asyncio.Lock] = {}
"""One lock per expert: extraction must never run twice in parallel for the same
expert (the harness memory middleware may extract the same session concurrently)."""


def _resolve_agent_scope(server: OctopServer, agent_id: str) -> tuple[Any, dict[str, Any]]:
    """The agent's workspace directory + its parsed ``config_json``."""
    services = server.services
    assert services is not None, "server.services required for memory backend"
    runtime = getattr(server, "app_runtime", None)
    registry = getattr(runtime, "agent_registry", None) if runtime is not None else None
    if registry is not None and hasattr(registry, "resolve_workspace_dir"):
        workspace = registry.resolve_workspace_dir(agent_id)
    else:
        paths = getattr(server, "paths", None) or services.paths
        workspace = paths.ensure_agent_workspace(agent_id)

    row = services.agent_repo.get(agent_id)
    cfg: dict[str, Any] = {}
    if row is not None and row.config_json:
        import json  # noqa: PLC0415

        try:
            parsed = json.loads(row.config_json)
            if isinstance(parsed, dict):
                cfg = parsed
        except json.JSONDecodeError:
            cfg = {}
    return workspace, cfg


def _open_memory(server: OctopServer, agent_id: str) -> Any:
    """Open the agent's ``Memory`` instance (sqlite by default, postgres opt-in)."""
    from octop_memory.core import Memory  # noqa: PLC0415

    services = server.services
    assert services is not None, "server.services required for memory backend"
    workspace, cfg = _resolve_agent_scope(server, agent_id)

    ns, backend, backend_config = open_memory_kwargs(
        agent_id=agent_id,
        cfg=cfg,
        octop_config=services.config,
        workspace_dir=workspace,
    )
    return Memory(namespace=ns, backend=backend, backend_config=backend_config)


def _memory_runtime(server: OctopServer, agent_id: str) -> Any:
    """Capture/search runtime for this expert.

    Prefers the live ``MemoryService`` runtime so the expert's own capture /
    privacy config applies; falls back to a default-configured runtime over the
    on-disk memory when the expert is not loaded (redaction is on by default).
    """
    from octop_memory.application.runtime import MemoryRuntime  # noqa: PLC0415

    runtime = getattr(server, "app_runtime", None)
    registry = getattr(runtime, "agent_registry", None) if runtime is not None else None
    service = _live_memory_service(registry, agent_id) if registry is not None else None
    service_runtime = getattr(service, "_runtime", None) if service is not None else None
    if service_runtime is not None:
        return service_runtime
    return MemoryRuntime(_open_memory(server, agent_id))


def _dashboard_bridge(memory: Any) -> Any:
    """Open the harness-memory JSON-RPC bridge over ``memory``.

    The same adapter the memory panel reaches through
    ``api/common/memory_client.call_memory_rpc``, so the MCP and the dashboard
    can never drift apart on candidate review semantics.
    """
    from octop_memory.adapters.bridge.handlers import Bridge  # noqa: PLC0415

    return Bridge(memory)


def _bridge_rpc(bridge: Any, method: str, params: dict[str, Any]) -> dict[str, Any]:
    """Call one dashboard RPC and return its result, raising ``ValueError`` on error."""

    def _invoke() -> dict[str, Any]:
        response = bridge.handle({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        error = response.get("error")
        if error:
            raise ValueError(error.get("message") or f"memory rpc {method!r} failed")
        return response.get("result") or {}

    return _invoke()


def _snippet(text: str) -> str:
    """Cap a raw event body so ``memory_search`` hits stay small."""
    body = (text or "").strip()
    return body if len(body) <= _SNIPPET_CHARS else body[: _SNIPPET_CHARS - 1].rstrip() + "…"


def _lookup_raw_users(memory: Any, hits: list[dict[str, Any]]) -> dict[str, str]:
    """``{raw event id: user}`` for the raw hits — the raw layer carries the sender."""
    ids = [
        str(hit.get("source_id"))
        for hit in hits
        if hit.get("layer") == "raw" and hit.get("source_id")
    ]
    if not ids:
        return {}
    try:
        events = memory.get_raw_events_by_ids(list(dict.fromkeys(ids)))
    except Exception:  # noqa: BLE001 - attribution must never break search
        logger.warning("memory_search: raw attribution lookup failed", exc_info=True)
        return {}
    return {str(event.id): str(event.user or "") for event in events}


def _prefer_personal(memory: Any, hits: list[dict[str, Any]], caller: str) -> list[dict[str, Any]]:
    """Stable-partition hits: *caller*'s first, then everyone else's.

    A preference, not a filter — memory is team-shared. Atoms/pages carry no
    sender column (external writes no longer stamp a name into the body), so only
    raw hits can be marked personal.
    """
    raw_users = _lookup_raw_users(memory, hits)
    mine: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for hit in hits:
        personal = (
            hit.get("layer") == "raw" and raw_users.get(str(hit.get("source_id")), "") == caller
        )
        hit["personal"] = personal
        if hit.get("layer") == "raw" and str(hit.get("source_id")) in raw_users:
            hit["user"] = raw_users[str(hit.get("source_id"))] or None
        (mine if personal else rest).append(hit)
    return [*mine, *rest]


def _prefer_personal_events(events: list[Any], caller: str) -> list[Any]:
    """Same preference for raw events (``corpus=raw``): own rows first, stable order."""
    mine = [event for event in events if str(getattr(event, "user", "") or "") == caller]
    rest = [event for event in events if str(getattr(event, "user", "") or "") != caller]
    return [*mine, *rest]


def _pipeline_hits(
    memory: Any,
    query: str,
    max_results: int,
    *,
    atom_only: bool,
    caller: str = "",
) -> list[dict[str, Any]]:
    """Run the in-process multi-source search and return its path-carrying hits."""
    from octop_memory.application.runtime import MemoryRuntime  # noqa: PLC0415

    runtime = MemoryRuntime(memory)
    result = runtime.memory_search(
        {
            "query": query,
            "maxResults": max_results * 4 if (atom_only or caller) else max_results,
            "corpus": "memory",
        }
    )
    hits = list(result.get("hits") or [])
    if atom_only:
        hits = [hit for hit in hits if hit.get("layer") == "atom"]
    if caller:
        hits = _prefer_personal(memory, hits, caller)
    return hits[:max_results]


def _caller_name() -> str:
    """Octop user name resolved from this request's token (never a client header)."""
    return _current_user_name.get() or f"user:{_current_user_id.get()}"


def _agent_row(server: OctopServer) -> Any:
    """The agent row bound to this request (validated by ``_AgentRouter``)."""
    services = server.services
    assert services is not None, "server.services required for memory MCP"
    row = services.agent_repo.get(_current_agent_id.get())
    if row is None:
        raise RuntimeError("X-Octop-Agent-Id header not bound to a known expert")
    return row


def _assert_expert_owner(server: OctopServer) -> None:
    """Review/ops tools are expert-owner (or admin) only."""
    row = _agent_row(server)
    user_id = _current_user_id.get()
    if _is_admin(server, user_id):
        return
    if row.user_id is None or row.user_id != user_id:
        raise PermissionError(
            "this tool is limited to the expert owner; external agents may use "
            "memory_search / memory_get / memory_save / memory_capture"
        )


def _is_admin(server: OctopServer, user_id: int | None) -> bool:
    user = _user_of(server, user_id)
    return bool(getattr(user, "is_admin", False))


def _user_of(server: OctopServer, user_id: int | None) -> Any:
    if user_id is None:
        return None
    manager = getattr(server, "user_manager", None)
    if manager is None:
        return None
    try:
        return manager.get_by_id(user_id)
    except Exception:  # noqa: BLE001 - auth failures surface as "unknown user"
        return None


def _user_may_access_agent(server: OctopServer, row: Any, user: Any) -> bool:
    """Owner / shared-expert visibility check (same rule as the HTTP routers).

    Kept in ``infra/`` so ``infra/agents`` does not import ``api/``.
    """
    if user is None:
        return False
    if getattr(user, "is_admin", False):
        return True
    if row.user_id is not None and row.user_id == getattr(user, "id", None):
        return True
    if int(getattr(row, "is_shared", 0) or 0) != 1:
        return False
    services = server.services
    repos = getattr(services, "repos", None) if services is not None else None
    if repos is None:
        return False
    from octop.infra.users.groups import expert_visible_to  # noqa: PLC0415

    return bool(expert_visible_to(repos, row, user_id=user.id, is_admin=False))


def build_memory_mcp(server: OctopServer) -> FastMCP:
    """Build the shared memory MCP app (expert bound per request, not per build)."""
    mcp = FastMCP(
        "octop-memory",
        # Stateless streamable HTTP: every request gets a fresh transport, no
        # Mcp-Session-Id tracking, so a server restart cannot orphan client
        # sessions with -32600 "Session not found".
        stateless_http=True,
        # Octop runs behind a reverse proxy (Host is the public domain), so the
        # mcp SDK's localhost DNS-rebinding protection does not apply.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    # Collapse the streamable-HTTP path to "/" so the endpoint is exactly
    # /mcp/memory (the default "/mcp" would make it /mcp/memory/mcp).
    mcp.settings.streamable_http_path = "/"

    def _agent_id() -> str:
        agent_id = _current_agent_id.get()
        if not agent_id:
            raise RuntimeError("X-Octop-Agent-Id header not bound to this request")
        return agent_id

    # ─── everyday tools (any user token scoped to the expert) ───────────────

    @mcp.tool()
    async def memory_search(
        query: str,
        max_results: int = 5,
        corpus: str = "all",
    ) -> dict[str, Any]:
        """**检索记忆（读入口）**：全文检索专家记忆，返回带虚拟路径的命中。

        每条命中带 ``path``，交给 ``memory_get`` 读全文；只想把背景拉进上下文就
        用 ``snippet``，要原话/证据用 ``memory_raws``（仅专家所有者）。

        Args:
            query: 自然语言问题/关键词（中文做 n-gram 分词）。
            max_results: 最多返回命中数，默认 5。
            corpus: ``all``（默认，原子优先、原始事件兜底）/ ``memory`` /
                ``atom``（只要长期记忆）/ ``raw``（只要原始事件，适合刚 capture
                还没提炼的内容）。
        """
        corpus_value = (corpus or "all").strip().lower()
        if corpus_value not in _SEARCH_CORPORA:
            raise ValueError(
                f"invalid corpus {corpus!r}; expected one of {sorted(_SEARCH_CORPORA)}"
            )
        caller = _caller_name()

        def _run() -> dict[str, Any]:
            memory = _open_memory(server, _agent_id())
            if corpus_value == "raw":
                from octop_memory.application.path_projection import (  # noqa: PLC0415
                    raw_to_path,
                )

                events = list(
                    memory.search_raw(query, limit=max_results * 4 if caller else max_results)
                )
                if caller:
                    events = _prefer_personal_events(events, caller)
                hits = [
                    {
                        "path": raw_to_path(event),
                        "layer": "raw",
                        "snippet": _snippet(event.content),
                        "occurred_at": event.timestamp.isoformat(),
                        "source_id": event.id,
                        "user": str(event.user or "") or None,
                        "personal": str(event.user or "") == caller,
                    }
                    for event in events[:max_results]
                ]
            else:
                hits = _pipeline_hits(
                    memory,
                    query,
                    max_results,
                    atom_only=corpus_value == "atom",
                    caller=caller,
                )
            return {
                "marker": "[octop memory search]",
                "hits": hits,
                "total": len(hits),
                "corpus": corpus_value,
                "caller": caller,
                "personal_hits": sum(1 for hit in hits if hit.get("personal")),
                "hint": (
                    "每条命中自带 path，可交给 memory_get(path) 读全文；"
                    "命中按「本次调用者相关」优先排序，团队共享内容不过滤"
                ),
            }

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def memory_get(
        path: str,
        start: int | None = None,
        lines: int | None = None,
    ) -> dict[str, Any]:
        """**读取记忆全文**：把 ``memory_search`` 命中的虚拟路径解析成 markdown。

        支持 ``atom/<id>.md`` / ``page/<entity>.md`` / ``raw/<date>/<id>.md``；
        长内容用 ``start`` / ``lines`` 分页。

        Args:
            path: 虚拟路径，取自 ``memory_search`` 的 ``hits[].path``。
            start: 可选起始行号（1-based）。
            lines: 可选返回行数。
        """
        from octop_memory.application.runtime import MemoryRuntime  # noqa: PLC0415

        def _run() -> dict[str, Any]:
            params: dict[str, Any] = {"path": path}
            if start is not None:
                params["from"] = start
            if lines is not None:
                params["lines"] = lines
            try:
                result = MemoryRuntime(_open_memory(server, _agent_id())).memory_get(params)
            except Exception as exc:  # stale / mistyped path from a previous call
                return {
                    "path": path,
                    "error": f"{exc.__class__.__name__}: {exc}",
                    "hint": (
                        "path 形如 atom/<atom_id>.md / page/<entity_id>.md / "
                        "raw/<YYYY-MM-DD>/<event_id>.md"
                    ),
                }
            return {
                "marker": "[octop memory get]",
                "path": result.get("path", path),
                "kind": result.get("kind"),
                "content": result.get("excerpt") or "",
                "total_lines": result.get("total_lines"),
                "from_line": result.get("from_line"),
                "to_line": result.get("to_line"),
                "truncated": result.get("truncated"),
                "metadata": result.get("metadata") or {},
            }

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def memory_save(
        content: str,
        source: str,
        topic: str | None = None,
        supersedes: str | None = None,
    ) -> dict[str, Any]:
        """**直接保存事实**：把一条已知事实写入长期记忆（跳过提炼，立即可召回）。

        用于明确、需长期记住的事实（用户偏好、项目约定）。日常对话内容请用
        ``memory_capture`` 交给提炼管线。

        旧事实过时了就用 ``supersedes`` 传旧记忆 id：旧记忆标记 deprecated，新事实
        立即生效。调用者身份由 token 决定，写进 ``metadata.caller``，不再拼进正文。

        Args:
            content: 要记住（或用来替代旧事实）的内容。
            source: 谁记录的（如 ``coding-agent``），用于追溯。
            topic: 可选主题标签。
            supersedes: 可选——被这条新事实取代的旧记忆 id。
        """
        caller = _caller_name()
        agent_id = _agent_id()
        service = _require_live_service(server, agent_id)

        def _run() -> dict[str, Any]:
            metadata: dict[str, Any] = {
                "source": source,
                "source_host": source,
                "caller": caller,
            }
            deprecated: bool | None = None
            memory = getattr(service, "memory", None)
            if supersedes:
                if memory is None:
                    raise RuntimeError("memory backend unavailable for supersedes")
                deprecated = memory.deprecate_atom(
                    supersedes, actor="user", note="superseded by memory_save"
                )
                metadata["supersedes"] = supersedes
            node = service.save(content, topic=topic, metadata=metadata)
            result: dict[str, Any] = {
                "node_id": node.id,
                "content": node.content,
                "source": source,
                "caller": caller,
            }
            if supersedes:
                result["deprecated"] = deprecated
                result["superseded_atom_id"] = supersedes
            return result

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def memory_capture(
        content: str = "",
        source: str = "",
        session_id: str | None = None,
        assistant: str | None = None,
        thread_id: str | None = None,
        dry_run: bool = False,
        extract: bool = True,
        events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """**写入原始事件（L0）**：一轮对话或一段记录，交给提炼流水线。

        ``content`` 是用户侧/事实侧内容，``assistant`` 是助手回复；两者落在同一批
        事件里，提取器才能判断"助手建议是否被用户接受"。只记助手结论时 ``content``
        留空字符串。

        走 octop-memory 的 capture 应用层：敏感信息自动脱敏、过短/回声内容按策略丢弃。
        写入后立即能用 ``memory_search(corpus="raw")`` 查到，提炼成长期记忆后才回到常规
        检索。默认**不自动晋升**：外部写入先进入审核队列，由专家所有者审核。

        调用者身份由 token 决定并写进事件 metadata（``caller`` / ``source_host``）；
        **不要**再把名字写进正文。

        Args:
            content: 用户侧内容（或一条提炼过的事实）；只记助手结论时留空。
                提供 ``events`` 时可以整段省略。
            source: 谁记录的（如 ``claude-code`` / ``codex``），同时作为 L0 的 host。
            session_id: 可选会话 id；缺省派生 ``ext:{source}:{caller}``，同一段工作
                请保持稳定。
            assistant: 助手侧回复（可为空）。
            thread_id: 可选线程 id，透传给 L0。
            dry_run: 只解析不写入；返回将要写入的事件。
            extract: 写入后是否在后台触发提炼（默认 True）；专家停止时不会自动启动。
            events: 已由客户端解析好的事件列表（`event_type` / `content`，可选
                `payload` / `timestamp_iso`）；提供时跳过服务端解析，直接走
                `MemoryRuntime.capture`（脱敏、回声保护、长度限制照常生效）。
        """
        caller = _caller_name()
        agent_id = _agent_id()

        def _run() -> dict[str, Any]:
            # ---- pre-parsed events (client-side parsers): straight to the runtime
            if events is not None:
                payload: dict[str, Any] = {
                    "source": source,
                    "source_host": _current_token_name.get() or source,
                    "caller": caller,
                }
                normalized: list[dict[str, Any]] = []
                for item in events[:500]:
                    if not isinstance(item, dict):
                        continue
                    body = item.get("content")
                    if not isinstance(body, str) or not body.strip():
                        continue
                    event: dict[str, Any] = {
                        "event_type": str(item.get("event_type") or _USER_ROLE),
                        "content": body,
                        "payload": {**payload, **(item.get("payload") or {})},
                    }
                    timestamp_iso = item.get("timestamp_iso")
                    if isinstance(timestamp_iso, str) and timestamp_iso:
                        event["timestamp_iso"] = timestamp_iso
                    normalized.append(event)
                if not normalized:
                    raise ValueError("events is empty after dropping blank entries")
                effective_session = session_id or f"ext:{source or 'mcp'}:{caller}"
                if dry_run:
                    return {
                        "marker": "[octop memory capture]",
                        "recorded": False,
                        "dry_run": True,
                        "session_id": effective_session,
                        "events": [
                            {
                                "event_type": e["event_type"],
                                "content": e["content"],
                                "caller": caller,
                            }
                            for e in normalized
                        ],
                        "note": "dry run: parsed only, nothing written",
                    }
                result = _memory_runtime(server, agent_id).capture(
                    {
                        "session_id": effective_session,
                        "thread_id": thread_id,
                        "user": caller,
                        "host": source or "mcp-external",
                        "events": normalized,
                    }
                )
                accepted = int(result.get("accepted") or 0)
                return {
                    "marker": "[octop memory capture]",
                    "recorded": accepted > 0,
                    "session_id": effective_session,
                    "source": source,
                    "caller": caller,
                    "accepted": accepted,
                    "skipped": {
                        key.removeprefix("skipped_"): value
                        for key, value in result.items()
                        if key.startswith("skipped_") and value
                    },
                    "note": "client-parsed events recorded through MemoryRuntime.capture",
                }
            pending: list[dict[str, Any]] = []
            # ``source`` is self-reported by the caller; the token name is the
            # server-known client identity, so prefer it for provenance.
            source_host = _current_token_name.get() or source
            payload = {"source": source, "source_host": source_host, "caller": caller}
            if content.strip():
                pending.append({"event_type": _USER_ROLE, "content": content, "payload": payload})
            if assistant:
                pending.append(
                    {"event_type": _ASSISTANT_ROLE, "content": assistant, "payload": payload}
                )
            if not pending:
                raise ValueError("content and assistant are both empty; nothing to record")

            effective_session = session_id or f"ext:{source or 'mcp'}:{caller}"
            if dry_run:
                return {
                    "marker": "[octop memory capture]",
                    "recorded": False,
                    "dry_run": True,
                    "session_id": effective_session,
                    "events": [
                        {
                            "event_type": event["event_type"],
                            "content": event["content"],
                            "caller": caller,
                        }
                        for event in pending
                    ],
                    "note": "dry run: parsed only, nothing written",
                }

            runtime = _memory_runtime(server, agent_id)
            result = runtime.capture(
                {
                    "session_id": effective_session,
                    "thread_id": thread_id,
                    "user": caller,
                    "host": source or "mcp-external",
                    "events": pending,
                }
            )
            accepted = int(result.get("accepted") or 0)
            return {
                "marker": "[octop memory capture]",
                "recorded": accepted > 0,
                "session_id": effective_session,
                "source": source,
                "caller": caller,
                "accepted": accepted,
                "skipped": {
                    key.removeprefix("skipped_"): value
                    for key, value in result.items()
                    if key.startswith("skipped_") and value
                },
                "note": (
                    "raw (L0) events recorded; visible now via memory_search(corpus=raw), "
                    "promoted to long-term memory only after review/提炼"
                ),
            }

        result = await asyncio.to_thread(_run)
        if extract and not dry_run and result.get("recorded"):
            result["extract_scheduled"] = _schedule_extract(
                server,
                agent_id,
                str(result["session_id"]),
                promote=_expert_extract_promote(server, agent_id),
            )
        return result

    # ─── review & ops tools (expert owner only) ─────────────────────────────

    @mcp.tool()
    async def memory_raws(
        query: str | None = None,
        session_id: str | None = None,
        host: str | None = None,
        user: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """**查原始事件（仅专家所有者）**：FTS 搜索或结构化过滤 L0 原始事件。

        Args:
            query: FTS 关键词（可选）。
            session_id: 按会话过滤。
            host: 按记录主机过滤（如 ``claude-code``）。
            user: 按调用者过滤。
            limit: 最多返回条数，默认 50。
        """
        _assert_expert_owner(server)

        def _run() -> dict[str, Any]:
            memory = _open_memory(server, _agent_id())
            events = (
                memory.search_raw(query, limit=limit)
                if query
                else memory.list_raw(
                    session_id=session_id,
                    host=host,
                    user=user or _caller_name(),
                    limit=limit,
                )
            )
            return {
                "events": [
                    {
                        "event_id": e.id,
                        "timestamp": e.timestamp.isoformat(),
                        "session_id": e.session_id,
                        "user": e.user,
                        "event_type": e.event_type,
                        "source": (e.payload or {}).get("source") if e.payload else None,
                        "content": e.content,
                    }
                    for e in events
                ],
                "count": len(events),
            }

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def memory_candidates(
        status: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """**查候选记忆（仅专家所有者）**：列出 L1 候选（默认 pending 队列）。

        Args:
            status: pending / promoted / rejected / needs_review / conflict。
            session_id: 按来源会话过滤。
            limit: 最多返回条数，默认 50。
        """
        _assert_expert_owner(server)
        from octop_memory.core import CandidateStatus  # noqa: PLC0415

        status_value: str | None = None
        if status:
            allowed = set(get_args(CandidateStatus))
            if status not in allowed:
                raise ValueError(
                    f"invalid candidate status {status!r}; expected one of {sorted(allowed)}"
                )
            status_value = status

        def _run() -> dict[str, Any]:
            candidates = _open_memory(server, _agent_id()).list_candidates(
                status=status_value,
                session_id=session_id,
                limit=limit,
            )
            return {
                "candidates": [
                    {
                        "candidate_id": c.id,
                        "status": c.status.value if hasattr(c.status, "value") else str(c.status),
                        "candidate_type": getattr(c, "candidate_type", None),
                        "assertion": getattr(c, "assertion", None),
                        "session_id": getattr(c, "session_id", None),
                        "confidence": getattr(c, "confidence", None),
                    }
                    for c in candidates
                ],
                "count": len(candidates),
            }

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def memory_extract(
        session_id: str | None = None,
        promote: bool | None = None,
    ) -> dict[str, Any]:
        """**手动触发提炼（仅专家所有者）**：把 L0 事件提炼为候选。

        专家未运行时直接返回错误（不会为了提炼而启动专家，避免意外模型开销）。

        Args:
            session_id: 只提炼该会话；缺省为 ``manual``。
            promote: 是否对候选执行晋升检查；缺省跟随专家自己的提炼配置（外部写入
                默认进入审核队列）。
        """
        _assert_expert_owner(server)
        agent_id = _agent_id()
        service = _require_live_service(server, agent_id)
        effective_session = session_id or "manual"
        effective_promote = (
            _expert_extract_promote(server, agent_id) if promote is None else bool(promote)
        )

        def _run() -> dict[str, Any]:
            result = service.extract(
                effective_session,
                incremental=True,
                promote=effective_promote,
                regen_pages=False,
            )
            if not isinstance(result, dict):
                return {
                    "session_id": effective_session,
                    "candidates": 0,
                    "promoted": 0,
                    "promote": effective_promote,
                }
            promotion = result.get("promotion")
            return {
                "session_id": effective_session,
                "events_considered": result.get("events_considered", 0),
                "candidates": result.get("candidates", 0),
                "promoted": promotion.get("promoted", 0) if isinstance(promotion, dict) else 0,
                "promote": effective_promote,
                "error": result.get("failure_reason"),
                "promotion": promotion,
            }

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def memory_promote(candidate_ids: list[str]) -> dict[str, Any]:
        """**采纳候选（仅专家所有者）**：与记忆面板「采纳」同一套实现。

        Args:
            candidate_ids: 要采纳的候选 id 列表（来自 ``memory_candidates``）。
        """
        _assert_expert_owner(server)
        bridge = _dashboard_bridge(_open_memory(server, _agent_id()))

        def _run() -> dict[str, Any]:
            totals = dict.fromkeys(
                ("promoted", "merged", "conflicts", "needs_review", "dropped", "llm_calls"),
                0,
            )
            candidates: list[dict[str, Any]] = []
            errors: list[dict[str, Any]] = []
            for candidate_id in candidate_ids:
                try:
                    detail = _bridge_rpc(
                        bridge, "promote_candidate", {"candidate_id": candidate_id}
                    )
                except Exception as exc:  # noqa: BLE001 - 逐条隔离，错误原样回给调用方
                    errors.append({"candidate_id": candidate_id, "error": str(exc)})
                    continue
                candidates.append({"candidate_id": candidate_id, **detail})
                for key in totals:
                    totals[key] += int(detail.get(key) or 0)
            return {**totals, "candidates": candidates, "errors": errors}

        return await asyncio.to_thread(_run)

    @mcp.tool()
    async def memory_reject(
        candidate_id: str,
        reason: str = "rejected by external caller",
        actor: str | None = None,
    ) -> dict[str, Any]:
        """**忽略候选（仅专家所有者）**：与记忆面板「忽略」同一套实现。

        Args:
            candidate_id: 候选 id。
            reason: 忽略原因（写入 journal note）。
            actor: 决策者，缺省 ``user``；可选 ``auto`` / ``rule``。
        """
        _assert_expert_owner(server)
        params: dict[str, Any] = {"candidate_id": candidate_id}
        if reason:
            params["reason"] = reason
        if actor:
            params["actor"] = actor

        def _run() -> dict[str, Any]:
            result = _bridge_rpc(
                _dashboard_bridge(_open_memory(server, _agent_id())),
                "reject_candidate",
                params,
            )
            return {"ok": True, **result}

        return await asyncio.to_thread(_run)

    return mcp


def _memory_service_of(agent: Any) -> Any | None:
    """``MemoryService`` on a live harness agent, or ``None`` when memory is off."""
    runtime = getattr(agent, "_memory_runtime", None)
    return getattr(runtime, "service", None) if runtime is not None else None


def _live_memory_service(registry: Any, agent_id: str) -> Any | None:
    """Return the in-process ``MemoryService`` when the expert is already loaded."""
    get_agent = getattr(registry, "get_agent", None)
    if not callable(get_agent):
        return None
    try:
        agent = get_agent(agent_id)
    except Exception:  # noqa: BLE001 — not running / not found / harness down
        return None
    return _memory_service_of(agent)


def _require_live_service(server: OctopServer, agent_id: str) -> Any:
    """The expert's live ``MemoryService``; never starts a stopped expert.

    Starting an expert spends the owner's model budget, so the MCP layer refuses
    instead (the review asked not to auto-start experts).
    """
    runtime = getattr(server, "app_runtime", None)
    registry = getattr(runtime, "agent_registry", None) if runtime is not None else None
    service = _live_memory_service(registry, agent_id) if registry is not None else None
    if service is None:
        raise RuntimeError(
            f"expert {agent_id!r} is not running, so its MemoryService is unavailable; "
            "start the expert (or use memory_capture, which writes L0 without it)"
        )
    return service


def _expert_extract_promote(server: OctopServer, agent_id: str) -> bool:
    """Whether extraction should promote, following the expert's extraction config.

    Default is ``False``: external writes wait in the review queue. When the live
    ``MemoryService`` exposes its runtime config, use its ``promote`` value.
    """
    runtime = getattr(server, "app_runtime", None)
    registry = getattr(runtime, "agent_registry", None) if runtime is not None else None
    service = _live_memory_service(registry, agent_id) if registry is not None else None
    service_runtime = getattr(service, "_runtime", None) if service is not None else None
    cfg_fn = getattr(service_runtime, "_extraction_cfg", None)
    if callable(cfg_fn):
        try:
            return bool(cfg_fn().get("promote", False))
        except Exception:  # noqa: BLE001 - a foreign runtime must not break capture
            return False
    return False


def _schedule_extract(
    server: OctopServer,
    agent_id: str,
    session_id: str,
    *,
    promote: bool,
) -> bool:
    """Schedule a background extract (serialized per expert, never auto-starts)."""
    runtime = getattr(server, "app_runtime", None)
    registry = getattr(runtime, "agent_registry", None) if runtime is not None else None
    if registry is None:
        return False
    service = _live_memory_service(registry, agent_id)
    if service is None:
        logger.info(
            "memory extract skipped for agent %s session %s: expert not running",
            agent_id,
            session_id,
        )
        return False

    async def _run() -> None:
        lock = _EXTRACT_LOCKS.setdefault(agent_id, asyncio.Lock())
        async with lock:
            try:
                result = await asyncio.to_thread(
                    service.extract,
                    session_id,
                    incremental=True,
                    promote=promote,
                    regen_pages=True,
                )
            except Exception:  # noqa: BLE001 - background work must not crash the loop
                logger.warning(
                    "memory extract failed for agent %s session %s",
                    agent_id,
                    session_id,
                    exc_info=True,
                )
                return
            reason = _extract_failure_reason(result)
            if reason:
                logger.warning(
                    "memory extract failed for agent %s session %s: %s",
                    agent_id,
                    session_id,
                    reason,
                )

    try:
        task = asyncio.get_running_loop().create_task(_run())
    except RuntimeError:  # no running loop (sync test call path)
        logger.warning("memory extract not scheduled for agent %s: no running loop", agent_id)
        return False
    _EXTRACT_TASKS.add(task)
    task.add_done_callback(_EXTRACT_TASKS.discard)
    return True


def _extract_failure_reason(result: Any) -> str | None:
    """Return the failure reason reported by ``MemoryService.extract``, if any."""
    if not isinstance(result, dict):
        return None
    for key in ("failure_reason", "error"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


# ─── ASGI auth: user token -> user, then expert binding + access check ───────


async def _send_json(send: Any, status: int, body: dict[str, Any]) -> None:
    import json  # noqa: PLC0415

    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(payload)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


def _headers(scope: dict[str, Any]) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}


class _TokenAuthMiddleware:
    """Resolve the caller from a user-bound bearer token.

    The token is looked up by its sha256 hash and compared in constant time; the
    caller identity is the token's owner. ``X-Octop-User-Id`` is deliberately
    ignored — a client cannot name somebody else.
    """

    def __init__(self, app: Any, server: OctopServer) -> None:
        self._app = app
        self._server = server

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        headers = _headers(scope)
        auth = headers.get("authorization", "")
        provided = auth[7:].strip() if auth.startswith("Bearer ") else ""
        if not provided:
            provided = headers.get("x-octop-memory-token", "").strip()
        if not provided:
            await _send_json(send, 401, {"error": "missing bearer token"})
            return

        services = self._server.services
        repo = getattr(getattr(services, "repos", None), "memory_mcp_token_repo", None)
        if repo is None:
            await _send_json(send, 401, {"error": "token store unavailable"})
            return

        digest = hash_token(provided)
        row = repo.get_by_token_hash(digest)
        if row is None or not token_matches(provided, row.token_hash):
            await _send_json(send, 401, {"error": "invalid token"})
            return
        if row.revoked_at:
            await _send_json(send, 401, {"error": "token revoked"})
            return

        user = _user_of(self._server, row.user_id)
        if user is None:
            await _send_json(send, 401, {"error": "token owner not found"})
            return

        # Clients that identify themselves (``X-Octop-Client``) are counted per
        # token and can be refused; a request without the header is never
        # counted and never blocked, so existing clients keep working.
        client = headers.get("x-octop-client", "").strip()[:64]
        if client:
            try:
                repo.record_client(row.token_id, client)
            except Exception:  # noqa: BLE001 - usage stats must never fail a request
                logger.warning(
                    "memory MCP client stats update failed for token %s",
                    row.token_id,
                    exc_info=True,
                )
            if client in (row.disabled_clients or []):
                await _send_json(
                    send,
                    403,
                    {"error": "this client is disabled for this token", "client": client},
                )
                return

        user_id_cv = _current_user_id.set(int(row.user_id))
        user_name_cv = _current_user_name.set(str(getattr(user, "username", "") or row.user_id))
        token_name_cv = _current_token_name.set(row.name)
        scope_cv = _current_token_scope.set(list(row.expert_ids) if row.expert_ids else None)
        try:
            repo.touch(row.token_id)
            await self._app(scope, receive, send)
        finally:
            _current_token_scope.reset(scope_cv)
            _current_token_name.reset(token_name_cv)
            _current_user_name.reset(user_name_cv)
            _current_user_id.reset(user_id_cv)


class _AgentRouter:
    """Bind the request to one expert and check the token owner's access to it.

    The expert comes from ``X-Octop-Agent-Id`` when the client sends it. A token
    bound to exactly one expert is a 唯一令牌: it names the expert itself, so the
    client may omit the header. A token with no ``expert_ids`` and one covering
    several experts still needs the header — the request is rejected with 400
    rather than guessed at.

    The expert set is not snapshotted: existence / ``enabled`` / ownership are
    re-checked per request, so experts created, shared or disabled after process
    start take effect immediately.
    """

    def __init__(self, app: Any, server: OctopServer) -> None:
        self._app = app
        self._server = server

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        headers = _headers(scope)
        requested_agent_id = headers.get("x-octop-agent-id", "").strip()
        token_scope = _current_token_scope.get()
        if requested_agent_id:
            agent_id = requested_agent_id
        elif token_scope is not None and len(token_scope) == 1:
            agent_id = token_scope[0]
        else:
            hint = "either bind the token to a single expert, or send X-Octop-Agent-Id"
            body: dict[str, Any] = {"error": hint}
            if token_scope is not None:
                body["allowed_expert_ids"] = list(token_scope)
            await _send_json(send, 400, body)
            return

        services = self._server.services
        row = services.agent_repo.get(agent_id) if services is not None else None
        if row is None or not row.enabled:
            await _send_json(send, 404, {"error": "missing or unknown agent_id (X-Octop-Agent-Id)"})
            return

        user = _user_of(self._server, _current_user_id.get())
        if token_scope is not None and agent_id not in token_scope:
            await _send_json(
                send,
                403,
                {"error": "this token is not scoped to that expert", "agent_id": agent_id},
            )
            return
        if not _user_may_access_agent(self._server, row, user):
            await _send_json(
                send,
                403,
                {"error": "token owner cannot access that expert", "agent_id": agent_id},
            )
            return

        agent_cv = _current_agent_id.set(agent_id)
        try:
            await self._app(scope, receive, send)
        finally:
            _current_agent_id.reset(agent_cv)


def _chain_lifespan(previous: Any, managers: list[Any]) -> Callable[[Any], Any]:
    """Wrap the host lifespan so MCP session managers run without hiding hooks."""

    @asynccontextmanager
    async def _lifespan(app: Any) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            for manager in managers:
                await stack.enter_async_context(manager.run())
            if previous is not None:
                await stack.enter_async_context(previous(app))
            yield

    return _lifespan


def _memory_mcp_enabled() -> bool:
    """Mount only when ``OCTOP_MEMORY_MCP_ENABLED`` asks for it.

    Token existence no longer flips the mount on: the endpoint appears (or not)
    at process start, so an operator enables it once and every token created
    afterwards works without a restart.
    """
    flag = (os.environ.get("OCTOP_MEMORY_MCP_ENABLED") or "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def install_memory_mcp(app: Any, server: OctopServer) -> None:
    """Mount ``/mcp/memory`` and keep the host lifespan intact.

    Mounts only when ``OCTOP_MEMORY_MCP_ENABLED`` is on (fail-closed: an
    unconfigured instance exposes nothing). The MCP
    session managers are chained into the existing FastAPI lifespan instead of
    replacing it, so future startup/shutdown hooks keep working.
    """
    if not _memory_mcp_enabled():
        return
    services = server.services
    assert services is not None, "server.services required for memory MCP mount"

    mcp = build_memory_mcp(server)
    # _session_manager is created lazily by streamable_http_app(); read it only
    # after building, and drop None entries (stateless mode has none).
    streamable_app = mcp.streamable_http_app()
    managers = [mgr for mgr in (getattr(mcp, "_session_manager", None),) if mgr is not None]

    app.mount("/mcp/memory", _TokenAuthMiddleware(_AgentRouter(streamable_app, server), server))
    if managers:
        app.router.lifespan_context = _chain_lifespan(app.router.lifespan_context, managers)


__all__ = ["build_memory_mcp", "install_memory_mcp"]
