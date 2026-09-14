"""Expose Octop expert memory as an MCP server for external agents.

External agents (coding agents, bots) can read/write Octop expert memory over
MCP (Streamable HTTP), aligned with the in-process ``MemoryService``
capabilities. Every write stamps a ``source`` marker that can be traced back
on recall.

Expert binding: the endpoint is a single ``/mcp/memory`` mount; the expert is
selected per request via the ``X-Octop-Agent-Id`` header, validated against the
agent registry on every call — the caller never passes an agent id per tool
call, and the URL itself does not leak expert ids.

raw vs atom (aligned with ``MemoryService``):

* ``memory_capture`` -> ``add_raw``: writes an **L0 raw event**, which goes
  through the extraction pipeline (extract -> candidate -> promote -> atom).
  Use it to record raw conversations / events. The record is visible
  immediately via ``memory_raws``; ``memory_recall`` returns it only
  after extraction promotes it to an atom.
* ``memory_save`` -> ``store``: persists a structured fact directly into the
  canonical atom/tree (durable, no extraction). Use it when you already know
  the exact fact to remember.

Read surface (three tools, same storage as the in-process ``memory_search`` /
``memory_get`` exposed to Octop's own agents):

* ``memory_recall`` -> ``recall_for_prompt``: ranked, prompt-injectable text.
  L2 atoms first; ``page`` headlines are folded into atom hits; L0 raw is only
  a fallback (dropped as soon as any atom matches). Takes ``session_id`` /
  ``thread_id`` so an auto-inject hook can exclude the current session's raw and
  use the thread's active-entity stack for co-reference.
* ``memory_search`` -> ``MemoryRuntime.memory_search`` (``corpus=raw`` uses
  ``Memory.search_raw``): the same ranking, returned as hits that carry a
  virtual ``path`` instead of rendered markdown.
* ``memory_get`` -> ``MemoryRuntime.memory_get``: resolve that path to the full
  markdown (``atom/<id>.md`` / ``page/<entity_id>.md`` / ``raw/<date>/<id>.md``).

Recall echo guard: ``memory_capture`` drops content carrying a recall marker
(``_RECALL_ECHO_MARKERS``), the same rule ``MemoryRuntime.capture`` applies via
``skip_memory_echo`` — the MCP write path calls ``Memory.add_raw`` directly and
would otherwise capture a hook's own injected recall block as a new event.

Sender attribution: ``X-Octop-User-Id`` identifies the caller, and every write
(``memory_capture`` / ``memory_save`` / ``memory_update``) prefixes the content
with ``<user>说：``. harness-memory's ``AtomCard`` has no user column, so putting
the sender into the text is what makes it reach the atom, stay FTS-searchable
(a query naming the sender matches), and remain visible on recall.

Auth: independent token via ``OCTOP_MEMORY_MCP_TOKEN`` (fail-closed when
unset), enforced by the ASGI middleware in ``mount_memory_mcp``.
"""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from typing import Any, get_args

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context
from mcp.server.transport_security import TransportSecuritySettings

from octop.infra.agents.memory_backend import open_memory_kwargs
from octop.infra.server import OctopServer

logger = logging.getLogger(__name__)

# 当前 MCP HTTP 请求的绑定状态（由 _AgentRouter 中间件写入，工具读取）。
# stateless streamable HTTP 下 mcp SDK 不提供 ctx.request_context，故用 contextvar
# 跨 ASGI 中间件 → 工具传递：
#   - _current_agent_id:   本次请求绑定的 expert（X-Octop-Agent-Id 校验后写入）
#   - _current_caller_user: 调用者 user id（供 memory_capture/save 做 per-user 追溯）
_current_agent_id: ContextVar[str] = ContextVar("octop_mcp_agent_id", default="")
_current_caller_user: ContextVar[str] = ContextVar("octop_mcp_caller_user", default="")

_SEARCH_CORPORA: frozenset[str] = frozenset({"all", "memory", "atom", "raw"})
"""Corpora ``memory_search`` accepts. ``atom``/``raw`` are layer filters over the
recall pipeline; ``all``/``memory`` are the same pipeline without a filter."""

_SNIPPET_CHARS = 200

_RECALL_ECHO_MARKERS: tuple[str, ...] = (
    "## Memory Recall",
    "[memory] Earlier in this workspace",
)
"""Markers ``recall_for_prompt`` puts into its rendered block (legacy + current).

``MemoryRuntime.capture`` drops events containing these (``skip_memory_echo``) so the
host's own injection cannot be captured back as a new memory. The MCP write path calls
``Memory.add_raw`` directly and therefore has to apply the same rule itself.
"""


def _open_memory(server: OctopServer, agent_id: str) -> Any:
    """Open the agent's ``Memory`` instance (sqlite by default, postgres opt-in).

    Mirrors ``api.common.memory_client._open_memory_for_agent`` but stays in
    ``infra/`` (no api dependency). Workspace is resolved from the agent
    registry, falling back to the Octop default layout.
    """
    from harness_memory.core import Memory  # noqa: PLC0415

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

    ns, backend, backend_config = open_memory_kwargs(
        agent_id=agent_id,
        cfg=cfg,
        octop_config=services.config,
        workspace_dir=workspace,
    )
    return Memory(namespace=ns, backend=backend, backend_config=backend_config)


def _snippet(text: str) -> str:
    """Cap a raw event body so ``memory_search`` hits stay small (``memory_get`` reads the rest)."""
    body = (text or "").strip()
    return body if len(body) <= _SNIPPET_CHARS else body[: _SNIPPET_CHARS - 1].rstrip() + "…"


def _is_recall_echo(content: str) -> bool:
    """True when ``content`` is our own recall block coming back as a new event.

    Mirrors ``MemoryRuntime.capture``'s anti-feedback rule; without it a hook that
    injects ``memory_recall`` output and then captures the turn via MCP would feed the
    injected block back in, and each round would recall (and re-capture) more of it.
    """
    return any(marker in content for marker in _RECALL_ECHO_MARKERS)


def _attributed(content: str, caller: str) -> str:
    """Prefix the sender so the caller id lives inside the text.

    harness-memory's ``AtomCard`` has no user column, so the sender is stamped
    by writing ``<user>说：`` into the content itself: it then reaches the atom's
    assertion (manual writes) or its raw event (captured events), stays
    FTS-searchable, and shows up verbatim on recall. Already-prefixed content is
    left untouched so a re-capture cannot double it.
    """
    name = (caller or "").strip()
    if not name:
        return content
    prefix = f"{name}说："
    return content if content.startswith(prefix) else prefix + content


def _pipeline_hits(
    memory: Any, query: str, max_results: int, *, atom_only: bool
) -> list[dict[str, Any]]:
    """Run the in-process multi-source search and return its path-carrying hits.

    ``atom_only`` keeps just L2 atoms, so the request is widened first —
    otherwise raw hits could crowd the atoms out before the filter runs.
    """
    from harness_memory.application.runtime import MemoryRuntime  # noqa: PLC0415

    runtime = MemoryRuntime(memory)
    result = runtime.memory_search(
        {
            "query": query,
            "maxResults": max_results * 4 if atom_only else max_results,
            "corpus": "memory",
        }
    )
    hits = list(result.get("hits") or [])
    if atom_only:
        hits = [hit for hit in hits if hit.get("layer") == "atom"]
    return hits[:max_results]


def build_memory_mcp(server: OctopServer) -> FastMCP:
    """Build the shared memory MCP app (expert bound per request, not per build).

    The expert is selected at request time by ``X-Octop-Agent-Id`` (validated
    against the agent repo by ``_AgentRouter``) and carried to the tools via the
    ``_current_agent_id`` contextvar. A single app is shared by every expert, so
    agents created or disabled after process start are honored immediately —
    no process restart is needed to pick up new agents.
    """
    mcp = FastMCP(
        "octop-memory",
        # Stateless streamable HTTP: every request gets a fresh transport, no
        # Mcp-Session-Id tracking. Session state is in-memory per process, so a
        # server restart silently orphans every client session id and the next
        # tool call fails with -32600 "Session not found". Stateless mode
        # eliminates that failure class entirely (clients re-initialize per
        # request); the cost is one extra initialize per tool call.
        stateless_http=True,
        # Octop runs behind a reverse proxy (Host is the public domain, forwarded
        # by nginx), not a localhost dev scenario — the mcp SDK's localhost
        # DNS-rebinding protection does not apply and would reject the Host
        # with 421 unless the domain is allow-listed.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    # Collapse the streamable-HTTP path to "/" so the endpoint is exactly
    # /mcp/memory (the default "/mcp" would make it /mcp/memory/mcp).
    mcp.settings.streamable_http_path = "/"

    def _agent_id() -> str:
        """Agent bound to this request (set by ``_AgentRouter`` from the header)."""
        agent_id = _current_agent_id.get()
        if not agent_id:
            raise RuntimeError("X-Octop-Agent-Id header not bound to this request")
        return agent_id

    def _memory() -> Any:
        return _open_memory(server, _agent_id())

    def _caller_user(ctx: Any | None) -> str:
        """读取当前 MCP 请求的调用者 user id。

        优先级：显式 ``user`` 参数 → ``X-Octop-User-Id`` header（由
        ``_AgentRouter`` 中间件写入 contextvar）。stateless HTTP 下 mcp SDK
        不提供 ``ctx.request_context``，故不依赖它。
        """
        try:
            return _current_caller_user.get() or ""
        except Exception:  # noqa: BLE001
            return ""

    def _derive_session(source: str, user: str) -> str:
        """外部调用缺省 session_id 时派生稳定会话键。

        规则 ``ext:{source}:{user}``：同 source 同 user 的多次 capture 落入
        同一分组，harness 提取管线能聚合蒸馏成 atom；不同 source / 不同 user
        分开分组，避免混入彼此上下文。
        """
        return f"ext:{source or 'mcp'}:{user or 'anon'}"

    @mcp.tool()
    def memory_recall(
        query: str,
        limit: int = 5,
        session_id: str | None = None,
        thread_id: str | None = None,
        user: str | None = None,
        ctx: Context | None = None,  # type: ignore[type-arg]
    ) -> dict[str, Any]:
        """**召回专家记忆（读入口首选）**：把与 query 相关的记忆召回进上下文。

        每次对话/任务开始前先调一次。运行完整召回管线（分词 → 路由 → FTS →
        重排 → 去重 → token 预算），返回结构化片段 + 可直接注入 system prompt 的 markdown。
        自动注入（hook）场景建议传 ``session_id``：管线会据此把**本会话**的 raw 排除，
        避免"注入 → 被记录 → 下轮又召回"的回声。

        三个读工具怎么选：
        - 只想把相关背景拉进上下文 → 用本工具（一次调用，``rendered`` 直接可注入）。
        - 要**定位某条具体记忆并读全文** → ``memory_search`` 拿 ``path``，
          再 ``memory_get(path)`` 读完整 markdown（支持分页）。
        - 要**原话/证据**，或 ``memory_capture`` 刚写入、还没晋升成原子的内容 →
          ``memory_raws``（L0 全文检索，capture 后立即可见）。

        覆盖范围（与内置 ``memory_search`` 同一套管线）：L2 原子优先，``page``
        主题页标题会并入 atom 命中；L0 原始事件只做兜底——只要有原子命中，raw 就被
        整层丢弃。L1 候选不在召回范围内，请用 ``memory_candidates``。

        Args:
            query: 自然语言问题/关键词，整句传入（内部对中文做 n-gram 分词）。
            limit: 最多返回片段数，默认 5。
            session_id: 可选，当前会话 id。用于把本会话的 raw 从召回里排除（防回声）；
                与 ``memory_capture`` 传入的 ``session_id`` 一致才生效。
            thread_id: 可选，会话线程 id。用于共指消解（"那个项目" 靠该线程的
                active-entity stack）并把命中写回实体栈；不传则只做普通检索。
            user: 可选调用者 id（覆盖 ``X-Octop-User-Id`` 头）。
            ctx: MCP 注入的上下文（读取 ``X-Octop-User-Id`` 头）。
        """
        from harness_memory.pipeline.recall import recall_for_prompt  # noqa: PLC0415

        caller = user or _caller_user(ctx)
        memory = _memory()
        result = recall_for_prompt(
            memory,
            query,
            thread_id=thread_id,
            session_id=session_id,
            limit=limit,
        )
        return {
            "memories": [
                {
                    "source_id": s.source_id,
                    "timestamp": s.timestamp_iso,
                    "layer": s.layer,
                    "text": s.text,
                }
                for s in result.snippets
            ],
            "count": len(result.snippets),
            "rendered": result.rendered,
            "caller": caller or None,
        }

    @mcp.tool()
    def memory_search(
        query: str,
        max_results: int = 5,
        corpus: str = "all",
    ) -> dict[str, Any]:
        """**检索记忆（返回可下钻的 path）**：全文检索记忆，返回带虚拟路径的命中列表。

        与 ``memory_recall`` 走同一套召回/重排管线，区别是本工具不渲染 markdown，而是给
        每条命中一个 ``path``，交给 ``memory_get`` 读全文。要"引用出处/读全文"用
        search + get，只想"把背景拉进上下文"用 ``memory_recall``，要"原话/证据"用
        ``memory_raws``。

        Args:
            query: 自然语言问题/关键词（中文会做 n-gram 分词）。
            max_results: 最多返回命中数，默认 5。
            corpus: 检索范围：
                ``all``（默认）/``memory`` = 原子(L2)+原始事件(L0)同一套管线；
                ``atom`` = 只要 L2 原子命中；
                ``raw`` = 直接走 L0 全文检索，不受"有原子命中就丢 raw"的兜底策略影响，
                适合找刚 ``memory_capture``、还没晋升成原子的内容。
        """
        corpus_value = (corpus or "all").strip().lower()
        if corpus_value not in _SEARCH_CORPORA:
            raise ValueError(
                f"invalid corpus {corpus!r}; expected one of {sorted(_SEARCH_CORPORA)}"
            )
        memory = _memory()
        if corpus_value == "raw":
            from harness_memory.application.path_projection import raw_to_path  # noqa: PLC0415

            hits = [
                {
                    "path": raw_to_path(event),
                    "layer": "raw",
                    "snippet": _snippet(event.content),
                    "occurred_at": event.timestamp.isoformat(),
                    "source_id": event.id,
                }
                for event in memory.search_raw(query, limit=max_results)
            ]
        else:
            hits = _pipeline_hits(memory, query, max_results, atom_only=corpus_value == "atom")
        return {
            "hits": hits,
            "total": len(hits),
            "corpus": corpus_value,
            "hint": "每条命中自带 path，可交给 memory_get(path) 读全文",
        }

    @mcp.tool()
    def memory_get(
        path: str,
        start: int | None = None,
        lines: int | None = None,
    ) -> dict[str, Any]:
        """**读取记忆全文**：把 ``memory_search`` / ``memory_recall`` 命中的虚拟路径解析成 markdown。

        支持的路径形态：``atom/<atom_id>.md``（L2 原子）、``page/<entity_id>.md``
        （L3 主题页）、``raw/<YYYY-MM-DD>/<event_id>.md``（L0 原始事件）。长内容用
        ``start`` / ``lines`` 分页（配合返回的 ``total_lines`` / ``truncated``）。

        Args:
            path: 虚拟路径，取自 ``memory_search`` 的 ``hits[].path``。
            start: 可选起始行号（1-based）。
            lines: 可选返回行数。
        """
        from harness_memory.application.runtime import MemoryRuntime  # noqa: PLC0415

        params: dict[str, Any] = {"path": path}
        if start is not None:
            params["from"] = start
        if lines is not None:
            params["lines"] = lines
        try:
            result = MemoryRuntime(_memory()).memory_get(params)
        except Exception as exc:  # stale / mistyped path from a previous call
            return {
                "path": path,
                "error": f"{exc.__class__.__name__}: {exc}",
                "hint": (
                    "path 形如 atom/<atom_id>.md / page/<entity_id>.md / "
                    "raw/<YYYY-MM-DD>/<event_id>.md，取自 memory_search 的 hits[].path"
                ),
            }
        return {
            "path": result.get("path", path),
            "kind": result.get("kind"),
            "content": result.get("excerpt") or "",
            "total_lines": result.get("total_lines"),
            "from_line": result.get("from_line"),
            "to_line": result.get("to_line"),
            "truncated": result.get("truncated"),
            "metadata": result.get("metadata") or {},
        }

    @mcp.tool()
    def memory_save(
        content: str,
        source: str,
        topic: str | None = None,
        user: str | None = None,
        ctx: Context | None = None,  # type: ignore[type-arg]
    ) -> dict[str, Any]:
        """**直接保存事实**：把一条已知事实写入原子层（跳过提取，立即可召回）。

        用于明确、需长期记住的事实（如用户偏好、项目约定）。日常对话内容请用
        ``memory_capture`` 交给提取管线。来源写入 ``metadata.source``，调用者写入 ``metadata.user``；
        调用者 id 还会自动拼进内容前缀（``<user>说：…``），这样它随原子一起落库、可被检索、
        召回时直接可见——不要把名字重复写进 ``content``。

        Args:
            content: 要记住的事实。
            source: 谁记录的（如 "coding-agent"），用于追溯。
            topic: 可选主题标签。
            user: 可选调用者 id（覆盖 ``X-Octop-User-Id`` 头）。
            ctx: MCP 注入的上下文（读取 ``X-Octop-User-Id`` 头）。
        """
        caller = user or _caller_user(ctx)
        memory = _memory()
        node = memory.store(
            _attributed(content, caller),
            topic=topic,
            metadata={"source": source, **({"user": caller} if caller else {})},
        )
        return {
            "node_id": node.id,
            "content": node.content,
            "source": source,
            "user": caller or None,
        }

    @mcp.tool()
    def memory_capture(
        content: str,
        source: str,
        session_id: str | None = None,
        user: str | None = None,
        ctx: Context | None = None,  # type: ignore[type-arg]
    ) -> dict[str, Any]:
        """**记录原始事件**：把一条原始内容写入 L0，交给提取流水线。

        日常使用入口：记录对话/事件，经 提取 → 候选 → 晋升 → 原子 成为记忆。
        记录后立即可用 ``memory_raws`` 查询，晋升后才可被 ``memory_recall`` 召回。
        调用者 id（``X-Octop-User-Id``）会自动拼成内容前缀 ``<user>说：…``：发送者由此进入
        原子正文，既能被 FTS 直接搜到，也能在召回时一眼看出是谁说的——**不要**自己再
        写一遍名字。

        回声保护：内容里带 ``memory_recall`` 注入标记（``[memory] Earlier in this
        workspace`` / ``## Memory Recall``）时**不写入**，返回 ``skipped=recall_echo``。
        拼进 prompt 的召回块被整轮回采会形成"注入 → 采集 → 再召回"的放大环，故直接丢弃。

        Args:
            content: 原始对话/事件内容（不含发送者前缀）。
            source: 谁记录的，用于追溯。
            session_id: 可选会话 id，用于提取分组；缺省派生为 ``ext:{source}:{user}``。
                传了之后，``memory_recall`` 用同一个 id 就能把本会话的 raw 排除（防回声）。
            user: 可选调用者 id（覆盖 ``X-Octop-User-Id`` 头）。
            ctx: MCP 注入的上下文（读取 ``X-Octop-User-Id`` 头）。
        """
        caller = user or _caller_user(ctx)
        if _is_recall_echo(content):
            logger.info("memory_capture: dropped recall echo for agent %s", _agent_id())
            return {
                "recorded": False,
                "skipped": "recall_echo",
                "reason": (
                    "content contains a recall injection marker "
                    f"({_RECALL_ECHO_MARKERS[1]!r} / {_RECALL_ECHO_MARKERS[0]!r}); "
                    "dropped so our own recall output is not captured as a new event"
                ),
                "user": caller or None,
            }
        effective_session = session_id or _derive_session(source, caller)
        memory = _memory()
        stored_content = _attributed(content, caller)

        # Idempotent capture: skip if an identical raw event (same session +
        # content) already exists, so re-ingesting the same conversation does
        # not duplicate L0 events. Keeps downstream extraction re-runnable.
        try:
            for ev in memory.list_raw(session_id=effective_session, limit=1000):
                if getattr(ev, "content", None) == stored_content:
                    return {
                        "event_id": ev.id,
                        "content": ev.content,
                        "source": source,
                        "user": caller or None,
                        "session_id": effective_session,
                        "recorded": True,
                        "duplicate": True,
                        "note": ("raw (L0) event already present; skipped (idempotent capture)"),
                    }
        except Exception:  # noqa: BLE001
            # If duplicate detection fails, fall back to recording (safe).
            pass

        raw = memory.add_raw(
            stored_content,
            event_type="manual",
            host="mcp-external",
            session_id=effective_session,
            user=caller or None,
            payload={"source": source},
        )
        extract_scheduled = _trigger_extract(server, effective_session)
        return {
            "event_id": raw.id,
            "content": raw.content,
            "source": source,
            "user": caller or None,
            "session_id": effective_session,
            "recorded": True,
            "extract_scheduled": extract_scheduled,
            "note": (
                "raw (L0) event recorded; visible now via memory_raws, "
                "recallable via memory_recall after the extraction pipeline "
                "promotes it to an atom"
            ),
        }

    @mcp.tool()
    def memory_update(
        atom_id: str,
        new_content: str,
        source: str,
        note: str = "mcp update",
        user: str | None = None,
        ctx: Context | None = None,  # type: ignore[type-arg]
    ) -> dict[str, Any]:
        """**更新记忆**：废弃旧原子并写入新事实。

        用于旧记忆已过时、需替换的场景（如纠正事实）。旧原子标记 deprecated，
        新事实立即可被 ``memory_recall`` 召回，带 ``supersedes`` 关联。
        与 ``memory_save`` 一样，调用者 id 会自动拼进内容前缀（``<user>说：…``）。

        Args:
            atom_id: 要废弃的旧原子 id。
            new_content: 替代的新事实（不含发送者前缀）。
            source: 谁更新的，用于追溯。
            note: 废弃说明，默认 "mcp update"。
            user: 可选调用者 id（覆盖 ``X-Octop-User-Id`` 头）。
            ctx: MCP 注入的上下文（读取 ``X-Octop-User-Id`` 头）。
        """
        caller = user or _caller_user(ctx)
        memory = _memory()
        deprecated = memory.deprecate_atom(atom_id, actor="user", note=note)
        node = memory.store(
            _attributed(new_content, caller),
            metadata={
                "source": source,
                "supersedes": atom_id,
                **({"user": caller} if caller else {}),
            },
        )
        return {
            "deprecated": deprecated,
            "deprecated_atom_id": atom_id,
            "new_node_id": node.id,
            "source": source,
            "user": caller or None,
        }

    # ─── 记忆分层查询 + 流水线调度（L0/L1/L2）─────────────────────────
    # 参考 DSH 记忆工具集（memory_raws/candidates/atoms/extract/promote/reject），
    # 把记忆生产流水线的每个环节暴露为 MCP 工具，供外部调度。

    @mcp.tool()
    def memory_raws(
        query: str | None = None,
        session_id: str | None = None,
        host: str | None = None,
        user: str | None = None,
        limit: int = 50,
        ctx: Context | None = None,  # type: ignore[type-arg]
    ) -> dict[str, Any]:
        """**查原始事件**：FTS 搜索或结构化过滤 L0 原始事件（证据源）。

        ``query`` 走全文搜索（capture 后立即可见），``session_id``/``host``/``user``
        做结构化过滤，按时间倒序返回。

        Args:
            query: FTS 关键词（可选）。
            session_id: 按会话过滤（如 ``ext:review-bot:user-alice``）。
            host: 按记录主机过滤（如 ``mcp-external``）。
            user: 按调用者过滤。
            limit: 最多返回条数，默认 50。
            ctx: MCP 注入的上下文。
        """
        caller = user or _caller_user(ctx)
        memory = _memory()
        events = (
            memory.search_raw(query, limit=limit)
            if query
            else memory.list_raw(
                session_id=session_id,
                host=host,
                user=user or (caller or None),
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
            "caller": caller or None,
        }

    @mcp.tool()
    def memory_candidates(
        status: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """**查候选记忆**：列出 L1 候选（默认 pending 队列）。

        候选由 ``memory_capture``/``memory_extract`` 生成。可用 ``status`` 过滤
        （pending / promoted / rejected / needs_review / conflict）。

        Args:
            status: 候选状态过滤，默认 pending。
            session_id: 按来源会话过滤。
            limit: 最多返回条数，默认 50。
        """
        memory = _memory()
        from harness_memory.core import CandidateStatus  # noqa: PLC0415

        # ``CandidateStatus`` is a ``typing.Literal`` (not an Enum), so it cannot
        # be instantiated: ``CandidateStatus(status)`` raises ``TypeError``. The
        # backend stores status as a plain string, so validate the caller's value
        # against the literal and pass the string straight through.
        status_value: str | None = None
        if status:
            allowed = set(get_args(CandidateStatus))
            if status not in allowed:
                raise ValueError(
                    f"invalid candidate status {status!r}; expected one of {sorted(allowed)}"
                )
            status_value = status
        candidates = memory.list_candidates(
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

    @mcp.tool()
    def memory_extract(
        session_id: str | None = None,
        limit: int = 100,
        promote: bool = False,
    ) -> dict[str, Any]:
        """**手动触发提取**：把最近 L0 原始事件提取为候选（可选直达原子）。

        取最近 ``limit`` 条 L0 事件 → LLM 类型化提取 → 候选（pending）；
        ``promote=True`` 时对候选执行晋升检查（L1 → L2），跳过人工审核。

        Args:
            session_id: 仅提取该会话的事件；缺省提取最近全部。
            limit: 提取的最近原始事件数，默认 100。
            promote: 是否对候选直接晋升，默认 False。
        """
        runtime_server = server.app_runtime
        assert runtime_server is not None, "app_runtime required for memory extract"
        agent = runtime_server.agent_registry.get_agent(_agent_id())
        runtime = getattr(agent, "_memory_runtime", None)
        service = getattr(runtime, "service", None) if runtime else None
        if service is None:
            return {"error": "MemoryService unavailable (agent not running / no memory runtime)"}

        eff_session = session_id or "manual"
        result = service.extract(eff_session, incremental=True, promote=promote, regen_pages=False)
        if not isinstance(result, dict):
            return {"session_id": eff_session, "candidates": 0, "promoted": 0}
        return {
            "session_id": eff_session,
            "events_considered": result.get("events_considered", 0),
            "candidates": result.get("candidates", 0),
            "promoted": result.get("promoted", 0)
            if isinstance(result.get("promotion"), dict)
            else 0,
            "error": result.get("failure_reason"),
        }

    @mcp.tool()
    def memory_promote(
        candidate_ids: list[str],
        importance: str | None = None,
    ) -> dict[str, Any]:
        """**审核晋升候选**：把 L1 候选晋升为 L2 原子记忆。

        对指定候选执行 5 项晋升检查（规则路径），通过则写入原子并记录 journal。

        Args:
            candidate_ids: 要晋升的候选 id 列表（来自 ``memory_candidates``）。
            importance: 覆盖重要性（low/medium/high），默认保留。
        """
        memory = _memory()
        candidates = memory.list_candidates(limit=1000)
        by_id = {c.id: c for c in candidates}
        selected = [by_id[cid] for cid in candidate_ids if cid in by_id]
        if not selected:
            return {"promoted": 0, "skipped": len(candidate_ids)}
        result = memory.promote_candidates(selected)
        return {
            "promoted": result.promoted if hasattr(result, "promoted") else len(selected),
            "skipped": len(candidate_ids) - len(selected),
        }

    @mcp.tool()
    def memory_reject(
        candidate_id: str,
        reason: str = "rejected by external caller",
    ) -> dict[str, Any]:
        """**拒绝候选**：标记候选为 rejected 并写入原因（不进原子层，可审计）。

        Args:
            candidate_id: 候选 id。
            reason: 拒绝原因，默认 "rejected by external caller"。
        """
        memory = _memory()

        # ``CandidateStatus`` is a ``typing.Literal``, not an Enum, so
        # ``CandidateStatus.REJECTED`` does not exist. Pass the literal string.
        ok = memory.update_candidate_status(
            candidate_id,
            status="rejected",
            decided_by="mcp-external",
            promotion_reason=reason,
        )
        return {"ok": ok, "candidate_id": candidate_id, "status": "rejected"}

    return mcp


def _trigger_extract(server: OctopServer, session_id: str | None) -> bool:
    """Best-effort: asynchronously trigger the agent's memory extraction.

    Raw events written by MCP capture are not in the harness-agent extractor's
    tracked sessions, so they would never be distilled into atoms. Reuse the
    agent's in-process ``MemoryService`` (with the agent's configured extraction
    LLM) via ``agent._memory_runtime.service`` (no public entrypoint;
    best-effort). Returns whether an extract task was scheduled.
    """
    import asyncio

    agent_id = _current_agent_id.get()
    if not session_id or not agent_id:
        return False
    try:
        runtime_server = server.app_runtime
        assert runtime_server is not None, "app_runtime required for memory extract"
        agent = runtime_server.agent_registry.get_agent(agent_id)
        runtime = getattr(agent, "_memory_runtime", None)
        service = getattr(runtime, "service", None) if runtime else None
        if service is None:
            return False

        async def _extract() -> None:
            try:
                await asyncio.to_thread(
                    service.extract,
                    session_id,
                    incremental=True,
                    promote=True,
                    regen_pages=True,
                )
            except Exception:
                logger.warning("memory extract failed for session %s", session_id, exc_info=True)

        asyncio.create_task(_extract())
        return True
    except Exception:
        logger.debug("memory extract trigger skipped for agent %s", agent_id, exc_info=True)
        return False


def _memory_mcp_token() -> str | None:
    """Read the MCP auth token (empty string treated as unconfigured)."""
    return (os.environ.get("OCTOP_MEMORY_MCP_TOKEN") or "").strip() or None


class _TokenAuthMiddleware:
    """ASGI middleware enforcing ``Authorization: Bearer`` or ``X-Octop-Memory-Token``."""

    def __init__(self, app: Any, token: str) -> None:
        self._app = app
        self._token = token

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
        }
        auth = headers.get("authorization", "")
        provided = auth[7:].strip() if auth.startswith("Bearer ") else ""
        if not provided:
            provided = headers.get("x-octop-memory-token", "").strip()

        if provided != self._token:
            body = b'{"error":"unauthorized"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self._app(scope, receive, send)


class _AgentRouter:
    """ASGI dispatcher validating ``X-Octop-Agent-Id`` against the agent repo and
    forwarding to the single shared memory MCP app.

    The agent set is NOT snapshotted at startup: every request is checked against
    the agent repo (existence + ``enabled``), so agents created or disabled after
    process start take effect immediately (no restart required).
    """

    def __init__(self, app: Any, server: OctopServer) -> None:
        self._app = app
        self._server = server

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            return  # lifespan is wired into the host FastAPI manually; http only here

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
        }
        agent_id = headers.get("x-octop-agent-id", "").strip()
        services = self._server.services
        row = services.agent_repo.get(agent_id) if (services is not None and agent_id) else None
        if row is None or not row.enabled:
            body = b'{"error":"missing or unknown agent_id (X-Octop-Agent-Id)"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 404,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        # 把本次请求绑定的 expert 与调用者 user id 写入 contextvar，供工具读取
        # （stateless HTTP 下 mcp SDK 不提供 ctx.request_context）。
        agent_cv = _current_agent_id.set(agent_id)
        user = headers.get("x-octop-user-id", "").strip()
        token_cv = _current_caller_user.set(user)
        try:
            await self._app(scope, receive, send)
        finally:
            _current_caller_user.reset(token_cv)
            _current_agent_id.reset(agent_cv)


def mount_memory_mcp(app: Any, server: OctopServer) -> list[Any]:
    """Mount the memory MCP endpoint at ``/mcp/memory``; the expert is selected
    per request via the ``X-Octop-Agent-Id`` header (validated at request time;
    the URL stays uniform and does not leak expert ids).

    Does not mount when ``OCTOP_MEMORY_MCP_TOKEN`` is unset (fail-closed).
    Returns the session managers that must be initialized in the host FastAPI
    lifespan (``streamable_http_app`` task groups depend on it).
    """
    token = _memory_mcp_token()
    if token is None:
        return []

    services = server.services
    assert services is not None, "server.services required for memory MCP mount"
    mcp = build_memory_mcp(server)
    # IMPORTANT: _session_manager is created lazily by streamable_http_app().
    # Read it only AFTER building the ASGI app and drop None entries — in
    # stateless HTTP mode there is no session manager to keep alive, and reading
    # mcp._session_manager before streamable_http_app() yields None, which then
    # crashes the host FastAPI lifespan with "NoneType has no attribute 'run'".
    streamable_app = mcp.streamable_http_app()
    managers = [mgr for mgr in (mcp._session_manager,) if mgr is not None]

    app.mount(
        "/mcp/memory",
        _TokenAuthMiddleware(_AgentRouter(streamable_app, server), token),
    )
    return managers


__all__ = ["build_memory_mcp", "mount_memory_mcp"]
