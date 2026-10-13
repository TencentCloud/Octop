"""Expose Octop expert memory as an MCP server for external agents.

External agents (coding agents, bots) can read/write Octop expert memory over
MCP (Streamable HTTP), aligned with the in-process ``MemoryService``
capabilities. Every write stamps a ``source`` marker that can be traced back
on recall.

Expert binding: the endpoint is a single ``/mcp/memory`` mount; the expert is
selected at connect time via the ``X-Octop-Agent-Id`` header (one connection
binds one expert — the caller never passes an agent id per tool call).

raw vs atom (aligned with ``MemoryService``):

* ``memory_capture`` -> ``add_raw``: writes an **L0 raw event**, which goes
  through the extraction pipeline (extract -> candidate -> promote -> atom).
  Use it to record raw conversations / events. The record is visible
  immediately via ``memory_raws`` / ``memory_search(corpus="raw")``; the
  regular search returns it only after extraction promotes it to an atom.
* ``memory_save`` -> ``store``: persists a structured fact directly into the
  canonical atom/tree (durable, no extraction). Use it when you already know
  the exact fact to remember.

Read surface (three tools, same storage as the in-process ``memory_search`` /
``memory_get`` exposed to Octop's own agents):

* ``memory_search`` -> ``MemoryRuntime.memory_search`` (``corpus=raw`` uses
  ``Memory.search_raw``): ranked hits that carry a virtual ``path`` instead of
  rendered markdown. L2 atoms first; ``page`` headlines are folded into atom
  hits; L0 raw is only a fallback (dropped as soon as any atom matches).
* ``memory_raws`` -> L0 inspection: the raw events themselves, newest first.
* ``memory_get`` -> ``MemoryRuntime.memory_get``: resolve that path to the full
  markdown (``atom/<id>.md`` / ``page/<entity_id>.md`` / ``raw/<date>/<id>.md``).

Recall echo guard: ``memory_capture`` drops content carrying a marker from
``_SKIP_CONTENT_MARKERS``, the same rule ``MemoryRuntime.capture`` applies via
``skip_memory_echo`` — the MCP write path calls ``Memory.add_raw`` directly and
would otherwise capture a hook's own injected memory block as a new event.

Content markers: everything this service puts back into a conversation is tagged
``[octop memory <tool>]`` — today ``search`` / ``get`` / ``capture`` (the retired
``recall`` tool shares the prefix), emitted as the ``marker`` field of the tool
response and as the first line of the blocks our hooks inject (the hook prefixes
``[octop memory search]``). Filtering is
therefore one rule: drop anything containing ``_OWN_CONTENT_PREFIX``. Older markers
(``## Memory Recall`` / ``[memory] Earlier in this workspace`` / ``[octop-memory
hook]``) stay in the list because transcripts already on disk carry them.

Record shape: ``source`` decides what ``memory_capture`` received. A terminal name
(``claude-code``, later ``kiro`` / ``dsh``) means ``content`` is a whole session
transcript, parsed record by record. Anything else means one conversation turn:
``content`` is the user side, ``assistant`` the reply — mirroring in-process
``MemoryService.capture_turn``, so the extractor sees both sides in one batch.
The extractor prompt only receives ``event_id / event_type / content / timestamp /
session_id``, so the role has to come from the data: in transcript mode each record
carries it, in one-turn mode the field the text was passed in does. Role-less
``manual`` content would be read as a user-stated fact — which is why the old
hard-coded ``manual`` had to go.

Sender attribution: ``X-Octop-User-Id`` identifies the caller, and the one-turn
write path (``memory_capture`` / ``memory_save``) prefixes the content with
``<user>说：``. harness-memory's ``AtomCard`` has no user column, and the extractor
prompt only serialises ``event_id / event_type / content / timestamp / session_id``
— never the event's ``user`` — so putting the sender into the text is what makes it
reach the atom, stay FTS-searchable (a query naming the sender matches), and remain
visible on recall.

Naming: the ``user`` parameter is the caller **identity** (kept from the original
tool surface), *not* the user's utterance — the human side is ``content``. Upstream
``MemoryService.capture_turn`` names them the other way round (``user`` = message
content, ``user_id`` = identity); aligning with it would be a breaking rename, so
this tool deliberately keeps the historical names.

Only the *user* side is prefixed. An ``assistant`` side is the assistant's own
words and already identified by its ``event_type``; stamping it with ``<user>说：``
would record the assistant's reply as if the user had said it. A whole transcript
takes the terminal path instead, where every record keeps its own role and no
prefix is added at all.

Auth: independent token via ``OCTOP_MEMORY_MCP_TOKEN`` (fail-closed when
unset), enforced by the ASGI middleware in ``mount_memory_mcp``.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any, get_args

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context
from mcp.server.transport_security import TransportSecuritySettings

from octop.infra.agents.memory.backend import open_memory_kwargs
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

_TRANSCRIPT_SOURCES: dict[str, str] = {
    "claude-code": "claude-code",
    "kiro": "kiro",
    "dsh": "dsh",
    "codex": "codex",
    "cursor": "cursor",
}
_TRANSCRIPT_PATH_ROOTS: tuple[str, ...] = (
    "~/.claude/projects",
    "~/.kiro/sessions",
    "~/.dsh/sessions",
    "~/.codex/sessions",
    "~/.cursor",
)
"""Where ``memory_capture(transcript_path=…)`` may read from.

A terminal's ``mcp_tool`` hook can only pass the path (Claude Code substitutes
``${transcript_path}``), and that path is readable only by an MCP server running on
the same machine. The allow-list keeps that convenience from becoming a general
arbitrary-file read: anything outside these terminal session stores is refused.
"""


"""``source`` values whose payload is a whole session transcript, not one turn.

``source`` names the terminal, and the terminal decides the parser — so callers
pass only one of the two. Unknown sources mean plain text (one turn per call).
DSH sessions are zstd-compressed, so the client decompresses before uploading.
"""

_GZIP_B64_PREFIX = "H4sI"
"""``base64(gzip(…))`` always starts with this; a JSONL body always starts with ``{``.

Only consulted in transcript mode, so a plain-text capture can never be misread
as a compressed payload.
"""

_OWN_CONTENT_PREFIX = "[octop memory "
"""Uniform marker for anything this service puts back into a conversation.

Emitted as the ``marker`` field of the read/write tool responses a client may quote
back (``[octop memory search|get|capture|recall]``) and as the first line of blocks
our hooks inject. One substring rule — this prefix — recognizes all of them,
including tools added later.
"""

_LEGACY_ECHO_MARKERS: tuple[str, ...] = (
    "## Memory Recall",
    "[memory] Earlier in this workspace",
    "[octop-memory hook]",
)
"""Older markers still present in transcripts already on disk.

``## Memory Recall`` / ``[memory] Earlier in this workspace`` are what the upstream
recall render emits (and what ``MemoryRuntime.capture`` filters on);
``[octop-memory hook]`` is the pre-2026 hooks' instruction text. Kept so backfilling
old sessions filters exactly like the one-turn rule always did.
"""

_SKIP_CONTENT_MARKERS: tuple[str, ...] = (_OWN_CONTENT_PREFIX, *_LEGACY_ECHO_MARKERS)
"""Content carrying any of these is our own plumbing, never L0 evidence."""

_HOST_PLUMBING_MARKERS: tuple[str, ...] = (
    "<local-command-caveat>",
    "<system-reminder>",
    "Base directory for this skill:",
)
"""Text the terminal injects on its own account: instructions to itself and the
bundled skill documentation it pastes in. Not something the user said, and not this
service's output either — but the same kind of noise, so a transcript import drops it
**when it appears in a message event**. The same string inside a tool result is data
(the file that was read may quote it), so that check stays narrower.

Slash-command wrappers (``<command-name>`` / ``<command-message>`` / ``<command-args>``)
and ``<local-command-stdout>`` are deliberately **kept**: they record a user action and
its effect (``/model`` → which model got selected), which is worth remembering.

``_TRANSCRIPT_SKIP_MARKERS`` is what a transcript import actually applies."""

_TRANSCRIPT_SKIP_MARKERS: tuple[str, ...] = _SKIP_CONTENT_MARKERS + _HOST_PLUMBING_MARKERS
"""Everything a transcript import drops — kept for callers that filter themselves."""


def _looks_like_transcript(text: str) -> bool:
    """True when *text* plausibly is JSONL rather than one piece of prose.

    Terminal names are also free-form ``source`` values, so ``source="claude-code"``
    with a sentence must keep recording that sentence (as it did before transcripts
    existed) instead of being parsed into zero events and dropped.
    """
    return text.lstrip().startswith("{")


USER_ROLE = "user_message"
ASSISTANT_ROLE = "assistant_message"
"""The two roles one-turn capture writes. Only ``user_message`` carries the sender
prefix — the assistant side is already identified by its role."""


def _read_transcript_file(raw_path: str) -> str:
    """Read a transcript file handed over by a local ``mcp_tool`` hook.

    Raises ``ValueError`` when the path is outside the terminal session stores, is
    compressed (a hook script ships those as gzip+base64 instead), or is unreadable.
    """
    from pathlib import Path as _Path  # noqa: PLC0415

    candidate = _Path(raw_path).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"transcript_path is not readable: {raw_path!r} ({exc})") from exc
    allowed = [(_Path(root).expanduser().resolve()) for root in _TRANSCRIPT_PATH_ROOTS]
    if not any(resolved == root or root in resolved.parents for root in allowed):
        raise ValueError(
            "transcript_path must live under a terminal session store "
            f"({', '.join(_TRANSCRIPT_PATH_ROOTS)}); got {raw_path!r}"
        )
    if resolved.suffix == ".zstd":
        raise ValueError(
            "compressed transcripts must be sent as gzip+base64 content "
            "(the terminal's hook script does this); transcript_path supports plain JSONL"
        )
    return resolved.read_text(encoding="utf-8", errors="replace")


def _resolve_agent_scope(server: OctopServer, agent_id: str) -> tuple[Any, dict[str, Any]]:
    """The agent's workspace directory + its parsed ``config_json``.

    Shared by the memory backend resolution and the raw-session archive (both live
    under that workspace; the archive under its system dir, ``{workspace}/.octop/``).
    """
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


def _archive_uploaded_session(
    server: OctopServer,
    agent_id: str,
    *,
    text: str,
    source: str,
    session_id: str,
    user: str | None,
) -> str | None:
    """Append this upload to the agent's markdown archive of the raw session.

    L0 only keeps user / assistant messages, so the tool traffic and the scratchpad
    would otherwise be gone; the archive keeps the whole uploaded record for review at
    ``{workspace}/.octop/memory-sessions/<session_id>.md``. Best-effort by design — a
    read-only or full disk must not fail the capture.
    """
    try:
        from octop.infra.agents.memory_session_archive import (  # noqa: PLC0415
            ARCHIVE_DIRNAME,
            append_session,
        )
        from octop.infra.agents.workspace import host_system_dir  # noqa: PLC0415

        workspace, cfg = _resolve_agent_scope(server, agent_id)
        session_dir = host_system_dir(workspace, cfg) / ARCHIVE_DIRNAME
        path = append_session(session_dir, session_id=session_id, text=text, host=source, user=user)
        return str(path) if path else None
    except Exception:  # noqa: BLE001 - the archive must never break capture
        logger.warning("memory_capture: session archive failed", exc_info=True)
        return None


def _open_memory(server: OctopServer, agent_id: str) -> Any:
    """Open the agent's ``Memory`` instance (sqlite by default, postgres opt-in).

    Mirrors ``api.common.memory_client._open_memory_for_agent`` but stays in
    ``infra/`` (no api dependency). Workspace is resolved from the agent
    registry, falling back to the Octop default layout.
    """
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


def _dashboard_bridge(memory: Any) -> Any:
    """Open the harness-memory JSON-RPC bridge over ``memory``.

    This is the same adapter the memory panel reaches through
    ``api/common/memory_client.call_memory_rpc`` (``Bridge`` →
    ``octop_memory.application.dashboard_data``). Routing the MCP write tools
    through it keeps one implementation behind both entry points, so the MCP and
    the dashboard can never drift apart on candidate review semantics. The
    import stays in ``infra/`` on purpose: ``octop_memory`` directly, never
    ``octop.api``.
    """
    from octop_memory.adapters.bridge.handlers import Bridge  # noqa: PLC0415

    return Bridge(memory)


def _bridge_rpc(
    bridge: Any,
    method: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Call one dashboard RPC and return its result, raising ``ValueError`` on error.

    The message is the bridge's own, i.e. the very text the memory panel shows
    when the identical call fails there.
    """

    def _invoke() -> dict[str, Any]:
        response = bridge.handle({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        error = response.get("error")
        if error:
            raise ValueError(error.get("message") or f"memory rpc {method!r} failed")
        return response.get("result") or {}

    return _invoke()


def _snippet(text: str) -> str:
    """Cap a raw event body so ``memory_search`` hits stay small (``memory_get`` reads the rest)."""
    body = (text or "").strip()
    return body if len(body) <= _SNIPPET_CHARS else body[: _SNIPPET_CHARS - 1].rstrip() + "…"


def _is_recall_echo(content: str) -> bool:
    """True when ``content`` is our own memory block coming back as a new event.

    Mirrors ``MemoryRuntime.capture``'s anti-feedback rule; without it a hook that
    injects ``memory_search`` output and then captures the turn via MCP would feed the
    injected block back in, and each round would surface (and re-capture) more of it.
    """
    return any(marker in content for marker in _SKIP_CONTENT_MARKERS)


def _attributed(content: str, caller: str) -> str:
    """Prefix the sender so the caller id lives inside the text.

    harness-memory's ``AtomCard`` has no user column, so the sender is stamped by
    writing ``<user>说：`` into the content itself: it then reaches the atom's
    assertion (manual writes) or its raw event (captured events), stays
    FTS-searchable, and shows up verbatim on recall. One implementation, also used by
    the transcript importer (``claude_transcript.attribute_user``).
    """
    from octop.infra.agents.claude_transcript import attribute_user  # noqa: PLC0415

    return attribute_user(content, caller)


def _lookup_raw_users(memory: Any, hits: list[dict[str, Any]]) -> dict[str, str]:
    """``{raw event id: user}`` for the raw hits — the raw layer is where the sender lives.

    Atoms / pages have no user column (the sender is written into the body as
    ``<x>说：`` when it is captured), so a batched raw lookup is how a raw hit gets
    attributed. Best-effort: a failure only costs the ordering hint.
    """
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


def _is_personal_hit(hit: dict[str, Any], caller: str, raw_users: dict[str, str]) -> bool:
    """Whether this hit looks like it belongs to *caller*."""
    if hit.get("layer") == "raw":
        return raw_users.get(str(hit.get("source_id")), "") == caller
    # Atoms / pages: the capture-time ``<caller>说：`` prefix is the only sender signal.
    return f"{caller}说：" in str(hit.get("snippet") or "")


def _prefer_personal(memory: Any, hits: list[dict[str, Any]], caller: str) -> list[dict[str, Any]]:
    """Stable-partition hits: *caller*'s first, then everyone else's.

    A preference, not a filter — memory is team-shared, so another person's hit is
    still returned, just after this caller's own. Each hit is annotated with
    ``personal``; raw hits also carry the raw event's ``user``.
    """
    raw_users = _lookup_raw_users(memory, hits)
    mine: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for hit in hits:
        personal = _is_personal_hit(hit, caller, raw_users)
        hit["personal"] = personal
        if hit.get("layer") == "raw" and str(hit.get("source_id")) in raw_users:
            hit["user"] = raw_users[str(hit.get("source_id"))] or None
        (mine if personal else rest).append(hit)
    return [*mine, *rest]


def _prefer_personal_events(events: list[Any], caller: str) -> list[Any]:
    """Same preference for raw *events* (``corpus=raw``): own rows first, stable order."""
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
    """Run the in-process multi-source search and return its path-carrying hits.

    ``atom_only`` keeps just L2 atoms, so the request is widened first —
    otherwise raw hits could crowd the atoms out before the filter runs. A *caller*
    widens it too: the caller's hits are pulled to the front after the fetch, so the
    pool must be bigger than the final page.
    """
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

    def _observe_tool(
        tool: str,
        *,
        session_id: str | None = None,
        input_payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        fn: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        """Run one tool body.

        This fork ships no tracing backend, so *tool*, *session_id*,
        *input_payload* and *metadata* are accepted (and ignored) to keep every
        tool call site shaped the same as the upstream implementation.
        """
        return fn()

    @mcp.tool()
    def memory_search(
        query: str,
        max_results: int = 5,
        corpus: str = "all",
        user: str | None = None,
        ctx: Context | None = None,  # type: ignore[type-arg]
    ) -> dict[str, Any]:
        """**检索记忆（读入口）**：全文检索记忆，返回带虚拟路径的命中列表。

        每条命中带一个 ``path``，交给 ``memory_get`` 读全文；只想"把背景拉进上下文"
        就直接用命中里的 ``snippet``，要"原话/证据"用 ``memory_raws``。自动注入（hook）
        场景用的就是本工具：注入块以 ``[octop memory search]`` 开头，``memory_capture``
        按该标记丢弃回声，所以不会被当成新事件采回来。

        **按调用者偏好排序**：调用者 id 有值（``X-Octop-User-Id`` 头或显式 ``user``）时，
        这个人的命中排在最前、其他人的紧随其后 —— 只调顺序，**不过滤**：记忆是团队共享的，
        别人踩过的坑照样返回。归属判定：raw 命中看 raw 的 ``user`` 列；原子/主题页看正文里的
        ``<调用者>说：`` 前缀（那句话在 capture 时打进去的）。命中带 ``personal`` 布尔，
        raw 命中还带 ``user``；返回体有 ``caller`` 与 ``personal_hits``。

        Args:
            query: 自然语言问题/关键词（中文会做 n-gram 分词）。
            max_results: 最多返回命中数，默认 5。
            corpus: 检索范围：
                ``all``（默认）/``memory`` = 原子(L2)+原始事件(L0)同一套管线；
                ``atom`` = 只要 L2 原子命中；
                ``raw`` = 直接走 L0 全文检索，不受"有原子命中就丢 raw"的兜底策略影响，
                适合找刚 ``memory_capture``、还没晋升成原子的内容。
            user: 可选调用者 id（覆盖 ``X-Octop-User-Id`` 头）。
            ctx: MCP 注入的上下文（读取 ``X-Octop-User-Id`` 头）。
        """
        corpus_value = (corpus or "all").strip().lower()
        if corpus_value not in _SEARCH_CORPORA:
            raise ValueError(
                f"invalid corpus {corpus!r}; expected one of {sorted(_SEARCH_CORPORA)}"
            )
        caller = user or _caller_user(ctx)

        def _run() -> dict[str, Any]:
            memory = _memory()
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
                        **({"personal": str(event.user or "") == caller} if caller else {}),
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
                "caller": caller or None,
                "personal_hits": sum(1 for hit in hits if hit.get("personal")),
                "hint": (
                    "每条命中自带 path，可交给 memory_get(path) 读全文；"
                    "命中已按「本次调用者相关」优先排序（personal=true 的那批在前，团队共享内容不过滤）"
                ),
            }

        return _observe_tool(
            "search",
            input_payload={
                "query": query,
                "max_results": max_results,
                "corpus": corpus_value,
            },
            metadata={"caller": caller or None},
            fn=_run,
        )

    @mcp.tool()
    def memory_get(
        path: str,
        start: int | None = None,
        lines: int | None = None,
    ) -> dict[str, Any]:
        """**读取记忆全文**：把 ``memory_search`` 命中的虚拟路径解析成 markdown。

        支持的路径形态：``atom/<atom_id>.md``（L2 原子）、``page/<entity_id>.md``
        （L3 主题页）、``raw/<YYYY-MM-DD>/<event_id>.md``（L0 原始事件）。长内容用
        ``start`` / ``lines`` 分页（配合返回的 ``total_lines`` / ``truncated``）。

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

        return _observe_tool(
            "get",
            input_payload={"path": path, "start": start, "lines": lines},
            fn=_run,
        )

    @mcp.tool()
    def memory_save(
        content: str,
        source: str,
        topic: str | None = None,
        supersedes: str | None = None,
        user: str | None = None,
        ctx: Context | None = None,  # type: ignore[type-arg]
    ) -> dict[str, Any]:
        """**直接保存事实**：把一条已知事实写入原子层（跳过提取，立即可召回）。

        用于明确、需长期记住的事实（如用户偏好、项目约定）。日常对话内容请用
        ``memory_capture`` 交给提取管线。

        旧事实过时了就用 ``supersedes`` 传旧原子 id：旧原子标记 deprecated，新事实
        立即可被 ``memory_search`` 检索到并带上 ``supersedes`` 关联——"更正事实"就是
        保存新事实 + 声明它取代谁，不需要另一个工具。

        来源写入 ``metadata.source``，调用者写入 ``metadata.user``；调用者 id 还会自动
        拼进内容前缀（``<user>说：…``），这样它随原子一起落库、可被检索、召回时直接
        可见——不要把名字重复写进 ``content``。

        Args:
            content: 要记住（或用来替代旧事实）的内容。
            source: 谁记录的（如 "coding-agent"），用于追溯。
            topic: 可选主题标签。
            supersedes: 可选——被这条新事实取代的旧原子 id；给了就先把它标记 deprecated。
            user: 可选调用者 id（覆盖 ``X-Octop-User-Id`` 头）。
            ctx: MCP 注入的上下文（读取 ``X-Octop-User-Id`` 头）。
        """
        caller = user or _caller_user(ctx)

        def _run() -> dict[str, Any]:
            memory = _memory()
            metadata: dict[str, Any] = {
                "source": source,
                **({"user": caller} if caller else {}),
            }
            deprecated: bool | None = None
            if supersedes:
                deprecated = memory.deprecate_atom(
                    supersedes, actor="user", note="superseded by memory_save"
                )
                metadata["supersedes"] = supersedes
            node = memory.store(
                _attributed(content, caller),
                topic=topic,
                metadata=metadata,
            )
            result: dict[str, Any] = {
                "node_id": node.id,
                "content": node.content,
                "source": source,
                "user": caller or None,
            }
            if supersedes:
                result["deprecated"] = deprecated
                result["superseded_atom_id"] = supersedes
            return result

        return _observe_tool(
            "save",
            input_payload={
                "source": source,
                "topic": topic,
                "supersedes": supersedes,
                "content": content,
                "content_chars": len(content or ""),
            },
            metadata={"caller": caller or None},
            fn=_run,
        )

    @mcp.tool()
    def memory_capture(
        content: str,
        source: str,
        session_id: str | None = None,
        user: str | None = None,
        assistant: str | None = None,
        thread_id: str | None = None,
        dry_run: bool = False,
        extract: bool = True,
        tool_events: str = "none",
        transcript_path: str | None = None,
        ctx: Context | None = None,  # type: ignore[type-arg]
    ) -> dict[str, Any]:
        """**写入原始事件（L0）**：一轮对话或整段会话记录，交给提取流水线。

        记什么，由 ``source`` 决定——它既是谁记录的，也说明这批内容是哪种形态：

        - **终端 transcript**（``source="claude-code"`` / ``"kiro"``，将来还有 dsh）：
          ``content`` 是整份 session 文件，服务端按该终端的记录格式解析成多条 L0 事件
          （``user_message`` / ``assistant_message`` / ``tool_call`` / ``tool_result``）。
          真实会话 1~2MB，模型产不出这个参数，**由终端 hook 脚本调用**；以 ``H4sI``
          开头时自动按 gzip+base64 解码。靠 ``src_key`` 幂等，可每轮上传整份文件、
          只补新增轮次。**上传的原文另存一份可读归档**：
          ``{workspace}/.octop/memory-sessions/<session_id>.md``（增量追加、重发去重），
          那里保留 L0 会丢掉的工具调用 / 结果与 thinking，返回体的 ``session_archive``
          给出实际路径。
        - **其它 source**：``content`` 是本轮用户侧内容，``assistant`` 是助手回复
          （两条事件落在同一批里，提取器才能判断"助手建议是否被用户接受"）；
          只记助手结论时 ``content`` 留空字符串。

        鉴权、专家路由与用户归属都由 MCP 接入层按连接配置自动带上，工具本身不感知。
        记录后立即可用 ``memory_raws`` / ``memory_search(corpus="raw")`` 查询，
        晋升成原子后才回到常规检索结果里。

        调用者 id（``X-Octop-User-Id``）会自动拼成内容前缀 ``<user>说：…``：发送者由此进入
        原子正文，既能被 FTS 直接搜到，也能在召回时一眼看出是谁说的——**不要**自己再
        写一遍名字。两种形态都加：一轮对话形态的用户侧；transcript 形态的 ``user_message``
        （跳过 sidechain 记录——那是子代理的合成提示；助手侧与工具事件不加，role 已由
        ``event_type`` 表达）。

        回声保护（两层，都是为了断掉"注入 → 采集 → 再召回"的放大环）：

        1. 带记忆注入标记（``[octop memory …]`` / ``[memory] Earlier in this workspace`` /
           ``## Memory Recall``）的事件**不写入**；一轮对话形态下两条都是回声才整体
           返回 ``skipped=recall_echo``，transcript 形态下逐条丢弃并计入
           ``skipped_echo``。transcript 形态还会一并丢弃**我们自己的 hook 指令文本**
           （``[octop-memory hook]``）——那是提示词管道，不是用户说过的话。
        2. transcript 形态下还会丢弃**我们自己的记忆读工具**（``memory_search`` /
           ``memory_get`` / ``memory_raws`` / ``memory_candidates``，以及已下线的
           ``memory_recall``）产生的 ``tool_result``——那些内容本来就来自库，且调用方
           hook 自己拼注入块时未必带标记。丢弃条数见返回体的 ``skipped_own_results``。
        3. transcript 形态下同样丢弃**终端自己注入的文本**：``<system-reminder>``、
           ``<local-command-caveat>``、``Base directory for this skill:``（自带技能文档）。
           斜杠命令包装（``<command-name>`` / ``<command-message>`` / ``<command-args>``）
           与 ``<local-command-stdout>`` **保留**——那是用户动作及其结果。这一层只作用于
           **消息事件**：工具输出（读到的文件内容）里出现同样字符串只是数据，不能当注入丢。

        **写得越详细，流水线产出的记忆越多。** 提取是一次 LLM 调用：它只把"自洽、
        具体、能独立读懂"的段落拆成候选（Fact / Decision / Task / Preference /
        ConflictCandidate），再经晋升检查落成原子。标题式、抽象或只有结论词的记录
        通常产出 0 条候选——不是流水线丢了，而是里面没有可提取的事实。

        一条记录应尽量写全（有多少写多少）：

        - **谁说的**：一轮对话**一次调用**写完——``content`` 写用户原话，``assistant``
          写助手自己的结论/建议。角色由字段隐含，**不要把助手产出塞进 ``content``**，
          那会让提取器按高置信的"用户事实"入账。
        - **发生了什么**：背景 + 动作，而不是结论词（"修好了" → "把 X 文件的 Y 分支
          改成 Z，因为…"）。
        - **结论与决定**：做/不做什么，**保留否定与限定词原文**（"先不做 Replace"
          不能写成 "决定做 Augment"）。
        - **具体标识**：文件路径、表名、接口、MR/issue 号、版本、端口、配置项、
          数字与阈值——它们是后续召回和实体锚定的抓手。
        - **理由与权衡**：为什么这样定，放弃了什么。
        - **未决项**：遗留 TODO、待确认的问题。
        - 一次涉及多个互不相关的事实就**分多次 capture**，一次一个主题。

        正例（一轮一次，可产出 Fact / Decision 候选）::

            memory_capture(
                content="记忆这块先按上次说的，把 MCP 写入路径补齐",  # 用户原话
                assistant=(
                    "octop 记忆写入路径排查：memory_capture 直接调 Memory.add_raw，"
                    "绕过了 MemoryRuntime.capture 的隐私层，redact_secrets 不生效；"
                    "决定把 transcript 上传并进 memory_capture、角色由字段隐含，"
                    "涉及 src/octop/infra/agents/memory_mcp.py。未决：脱敏是否同分支一起修。"
                ),
                source="coding-agent",
                session_id="ext:dsh:demo-octop",
            )

        反例（几乎必然产出 0 条候选）::

            memory_capture(content="记忆有问题", source="coding-agent")

        两个角色的写法（**谁说的由字段决定**）：

        - ``content`` 是**人这一侧**的内容（用户原话，或一条提炼过的事实/结论）。落库为
          ``user_message``，并自动带 ``<调用者>说：`` 前缀——提取器只能看到 ``content``，
          前缀是"谁记录的"进入原子正文、可被 FTS 命中的唯一途径。
        - ``assistant`` 是**助手这一侧**的内容。落库为 ``assistant_message``，**不加前缀**：
          角色已由 ``event_type`` 表达，助手的话不能记成用户说的。
        - **整段会话（有人也有助手）别走这里**：用终端形态（``source="claude-code"`` /
          ``"kiro"`` / ``"dsh"``）上传 session 文件，每条记录自带 ``event_type``、不加任何
          前缀。纯文本形态的整段对话目前没有入口。

        Args:
            content: 一轮对话时的**人这一侧**内容（只记助手结论时留空字符串）；``source`` 是终端时
                是整份 transcript（以 ``H4sI`` 开头则自动按 gzip+base64 解码）。
            source: 谁记录的，用于追溯；同时说明内容形态——``claude-code`` / ``kiro`` / ``dsh``
                且内容确实是 JSONL（或以 ``H4sI`` 开头的 gzip+base64）时走该终端的 transcript
                parser；**终端名 + 普通文本会退回一轮对话记录**（老调用方不改也能用），其它
                ``source`` 一律按一轮对话处理；并作为 L0 的 ``host``
                （``memory_raws(host=…)`` 可筛）。
            assistant: 一轮对话时的**助手这一侧**回复（不加发送者前缀）；留空则该次只写人这一侧。
            session_id: 可选会话 id，用于提取分组；一轮对话缺省派生为 ``ext:{source}:{user}``，
                transcript 缺省为 ``cc:<transcript 的 sessionId>``。同一段工作请保持同一个
                id，跨调用稳定。
            thread_id: 可选线程 id，透传给 L0。
            dry_run: 只解析不写入，返回将要写入的条数 / 事件列表。
            extract: 写入后是否立即触发提取（默认 ``True``）。批量回灌传 ``False``，
                先只落 L0，再用 ``memory_extract`` 受控提取。
            transcript_path: 仅用于终端的 ``mcp_tool`` hook：Claude Code 会把
                ``${transcript_path}`` 原样传进来，由**同机的** MCP 服务端读取该文件
                （只允许终端会话目录：``~/.claude/projects`` / ``~/.kiro/sessions`` /
                ``~/.dsh/sessions``；``.zstd`` 不支持，需按 gzip+base64 传 content）。
                远程部署读不到调用方的文件，请改用 hook 脚本上报 content。
            tool_events: transcript 形态下**只决定落库哪些事件，不影响上传内容**——``content``
                始终是整份 transcript（hook 按增量上传，服务端解压后逐条解析）。
                ``none``（默认）只落 ``user_message`` / ``assistant_message``：L0 原始素材是
                提取流水线的输入与召回兜底层，工具流量占体积约 79%（``tool_result`` 一项 61%），
                留着会挤占每批候选预算、稀释召回内容。要保真复查再显式放开：``calls`` 只记
                ``tool_call``（知道 agent 做了什么、丢输出），``all`` 连 ``tool_result`` 一起记。
            user: 可选调用者 id（覆盖 ``X-Octop-User-Id`` 头）。
            ctx: MCP 注入的上下文（读取 ``X-Octop-User-Id`` 头）。
        """
        caller = user or _caller_user(ctx)

        def _run() -> dict[str, Any]:
            nonlocal content
            memory = _memory()

            # ---- terminal transcript: ``source`` names the terminal, it names the parser
            # A real session is 1~2MB, so it is shipped by the terminal's hook script
            # (no model could pass that as a tool argument) and gzipped+base64-encoded.
            if transcript_path and source in _TRANSCRIPT_SOURCES:
                content = _read_transcript_file(transcript_path)
            if source in _TRANSCRIPT_SOURCES and (
                content.startswith(_GZIP_B64_PREFIX) or _looks_like_transcript(content)
            ):
                from octop.infra.agents.claude_transcript import import_content  # noqa: PLC0415

                text = content
                if text.startswith(_GZIP_B64_PREFIX):
                    import base64  # noqa: PLC0415
                    import gzip  # noqa: PLC0415

                    try:
                        text = gzip.decompress(base64.b64decode(text)).decode("utf-8", "replace")
                    except Exception as exc:  # noqa: BLE001 - surface a usable message
                        raise ValueError(
                            f"content starts like gzip+base64 but cannot be decoded: {exc}"
                        ) from exc

                stats = import_content(
                    memory,
                    text,
                    session_id=session_id,
                    user=caller or None,
                    host=source,
                    dry_run=dry_run,
                    skip_markers=_SKIP_CONTENT_MARKERS,
                    skip_message_markers=_HOST_PLUMBING_MARKERS,
                    tool_events=tool_events,
                    parser=_TRANSCRIPT_SOURCES[source],
                )
                archive = None
                if not dry_run:
                    archive = _archive_uploaded_session(
                        server,
                        _agent_id(),
                        text=text,
                        source=source,
                        session_id=stats.session_id,
                        user=caller or None,
                    )
                extract_scheduled = bool(extract and not dry_run) and _trigger_extract(
                    server, stats.session_id
                )
                return {
                    "marker": "[octop memory capture]",
                    "session_id": stats.session_id,
                    "session_archive": archive,
                    "parsed": stats.parsed,
                    "imported": stats.imported,
                    "skipped_existing": stats.skipped_existing,
                    "skipped_echo": stats.skipped_echo,
                    "skipped_own_results": stats.skipped_own_results,
                    "skipped_tools": stats.skipped_tools,
                    "tool_events": tool_events,
                    "events_by_type": stats.by_type,
                    "sidechain": stats.sidechain,
                    "dry_run": dry_run,
                    "extract_scheduled": extract_scheduled,
                    "warnings": stats.warnings,
                    "note": (
                        "transcript parsed into L0 raw events; extraction runs off the request path, "
                        "so atoms show up only after promotion"
                        if extract_scheduled or dry_run
                        else (
                            "transcript parsed into L0 raw events; extraction skipped (extract=false) — "
                            "run memory_extract(session_id=…) in a paced sweep to promote them"
                        )
                    ),
                }

            # ---- one turn: the role is implied by which field the text is in ---------
            outgoing: list[tuple[str, str]] = []
            if content.strip():
                outgoing.append((USER_ROLE, content))
            if assistant:
                outgoing.append((ASSISTANT_ROLE, assistant))
            if not outgoing:
                raise ValueError("content and assistant are both empty; nothing to record")
            kept = [(role, body) for role, body in outgoing if not _is_recall_echo(body)]
            if not kept:
                logger.info("memory_capture: dropped recall echo for agent %s", _agent_id())
                return {
                    "marker": "[octop memory capture]",
                    "recorded": False,
                    "skipped": "recall_echo",
                    "reason": (
                        "every event carries a memory injection marker "
                        f"(e.g. {_OWN_CONTENT_PREFIX!r}); "
                        "dropped so our own injected block is not captured as a new event"
                    ),
                    "user": caller or None,
                }
            effective_session = session_id or _derive_session(source, caller)

            # Idempotent capture: reuse the existing raw event whenever the same
            # session + content + role is already present, so re-ingesting the same
            # conversation does not duplicate L0 events. Keeps extraction re-runnable.
            existing: dict[tuple[Any, Any], tuple[str, str]] = {}
            try:
                for ev in memory.list_raw(session_id=effective_session, limit=1000):
                    existing.setdefault(
                        (getattr(ev, "content", None), getattr(ev, "event_type", None)),
                        (ev.id, str(getattr(ev, "content", ""))),
                    )
            except Exception:  # noqa: BLE001
                # If duplicate detection fails, fall back to recording (safe).
                existing = {}

            recorded: list[dict[str, Any]] = []
            for role, body in kept:
                # Only the human side is attributed. ``event_type`` already marks the other
                # side as the assistant, and the extractor prompt only ever sees
                # event_id / event_type / content / timestamp / session_id — never the
                # ``user`` column — so the prefix is how a sender reaches the atom text.
                # Prefixing the assistant side would record the assistant's own words as
                # if the user had said them.
                stored_content = _attributed(body, caller) if role == USER_ROLE else body
                duplicate = existing.get((stored_content, role))
                if duplicate is not None:
                    event_id, event_content = duplicate
                    recorded.append(
                        {
                            "event_id": event_id,
                            "event_type": role,
                            "content": event_content,
                            "duplicate": True,
                        }
                    )
                    continue
                if dry_run:
                    recorded.append(
                        {
                            "event_id": None,
                            "event_type": role,
                            "content": stored_content,
                            "duplicate": False,
                        }
                    )
                    continue
                raw = memory.add_raw(
                    stored_content,
                    event_type=role,
                    host="mcp-external",
                    session_id=effective_session,
                    thread_id=thread_id,
                    user=caller or None,
                    payload={"source": source},
                )
                recorded.append(
                    {
                        "event_id": raw.id,
                        "event_type": role,
                        "content": raw.content,
                        "duplicate": False,
                    }
                )

            extract_scheduled = bool(extract and not dry_run) and _trigger_extract(
                server, effective_session
            )
            result: dict[str, Any] = {
                "marker": "[octop memory capture]",
                "event_id": recorded[0]["event_id"],
                "content": recorded[0]["content"],
                "events": recorded,
                "source": source,
                "user": caller or None,
                "session_id": effective_session,
                "event_type": kept[0][0],
                "thread_id": thread_id,
                "recorded": not dry_run,
                "dry_run": dry_run,
                "extract_scheduled": extract_scheduled,
                "note": (
                    "raw (L0) events recorded; visible now via memory_raws, "
                    "searchable via memory_search after the extraction pipeline "
                    "promotes them to atom(s)"
                ),
            }
            if source in _TRANSCRIPT_SOURCES:
                result["note"] = (
                    f"source {source!r} names a terminal, but content is not a transcript "
                    "(it does not start with a JSON record); recorded as one turn instead. "
                    "Pass the terminal's session file, or use a non-terminal source for text."
                )
            if dry_run:
                result["note"] = "dry run: parsed only, nothing written"
            elif all(item["duplicate"] for item in recorded):
                result["duplicate"] = True
                result["note"] = "raw (L0) event already present; skipped (idempotent capture)"
            return result

        return _observe_tool(
            "capture",
            session_id=session_id,
            input_payload={
                "source": source,
                "session_id": session_id,
                "thread_id": thread_id,
                "dry_run": dry_run,
                "extract": extract,
                "tool_events": tool_events,
                "content": content,
                "assistant": assistant,
                "content_chars": len(content or ""),
                "assistant_chars": len(assistant or "") if assistant else 0,
                "has_transcript_path": bool(transcript_path),
            },
            metadata={"caller": caller or None},
            fn=_run,
        )

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

        def _run() -> dict[str, Any]:
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

        return _observe_tool(
            "raws",
            session_id=session_id,
            input_payload={
                "query": query,
                "session_id": session_id,
                "host": host,
                "limit": limit,
            },
            metadata={"caller": caller or None},
            fn=_run,
        )

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
        from octop_memory.core import CandidateStatus  # noqa: PLC0415

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

        def _run() -> dict[str, Any]:
            memory = _memory()
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

        return _observe_tool(
            "candidates",
            session_id=session_id,
            input_payload={
                "status": status_value,
                "session_id": session_id,
                "limit": limit,
            },
            fn=_run,
        )

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
        # Prefer the unwrapped extract so MCP owns the root ``memory.extract``
        # span (and nested stages) without nesting another identical root.
        extract_fn = getattr(service, "_octop_memory_extract_inner", None) or service.extract

        def _run() -> dict[str, Any]:
            result = extract_fn(eff_session, incremental=True, promote=promote, regen_pages=False)
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
                "promotion": result.get("promotion"),
            }

        return _observe_tool(
            "extract",
            session_id=eff_session,
            input_payload={
                "session_id": eff_session,
                "limit": limit,
                "promote": promote,
            },
            fn=_run,
        )

    @mcp.tool()
    def memory_promote(candidate_ids: list[str]) -> dict[str, Any]:
        """**采纳候选**（与记忆面板「采纳」是同一套实现）。

        逐条走 dashboard 的 ``promote_candidate``：``pending`` 候选执行 5 项晋升
        检查（通过则写入原子，也可能落为 merge / conflict / needs_review），
        ``needs_review`` / ``conflict`` 候选按人工裁决强制转正（取决于所装的
        harness-memory 版本：0.9.9 起会同时 supersede 被顶替的旧原子）。状态不
        允许（已 promoted / rejected）或候选不存在时，该条以 ``errors`` 返回，不
        影响同批其它候选。

        Args:
            candidate_ids: 要采纳的候选 id 列表（来自 ``memory_candidates``）。

        Returns:
            与面板一致的聚合计数（promoted / merged / conflicts / needs_review /
            dropped / llm_calls）、逐条结果 ``candidates`` 与逐条错误 ``errors``；
            ``errors`` 非空即表示并非全部采纳成功，调用方必须检查。
        """
        bridge = _dashboard_bridge(_memory())

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
                        bridge,
                        "promote_candidate",
                        {"candidate_id": candidate_id},
                    )
                except Exception as exc:  # noqa: BLE001 - 逐条隔离，错误原样回给调用方
                    errors.append({"candidate_id": candidate_id, "error": str(exc)})
                    continue
                candidates.append({"candidate_id": candidate_id, **detail})
                for key in totals:
                    totals[key] += int(detail.get(key) or 0)
            return {**totals, "candidates": candidates, "errors": errors}

        return _observe_tool(
            "promote",
            input_payload={"candidate_ids": list(candidate_ids)},
            fn=_run,
        )

    @mcp.tool()
    def memory_reject(
        candidate_id: str,
        reason: str = "rejected by external caller",
        actor: str | None = None,
    ) -> dict[str, Any]:
        """**忽略候选**（与记忆面板「忽略」是同一套实现）。

        走 dashboard 的 ``reject_candidate``：只允许 pending / needs_review /
        conflict 的候选；置为 rejected 并记录 decided_by / decided_at 与一条
        ``action="reject"`` 的 journal（可审计），不触碰原子层。状态不允许或候选
        不存在时抛错，错误信息与面板提示一致。

        Args:
            candidate_id: 候选 id。
            reason: 忽略原因，写入 journal 的 note。
            actor: 决策者，缺省与面板一致取 ``user``；可选 ``auto`` / ``rule``。
        """
        params: dict[str, Any] = {"candidate_id": candidate_id}
        if reason:
            params["reason"] = reason
        if actor:
            params["actor"] = actor

        def _run() -> dict[str, Any]:
            result = _bridge_rpc(
                _dashboard_bridge(_memory()),
                "reject_candidate",
                params,
            )
            return {"ok": True, **result}

        return _observe_tool(
            "reject",
            input_payload=params,
            fn=_run,
        )

    return mcp


def _extract_failure_reason(result: Any) -> str | None:
    """Return the failure reason reported by ``MemoryService.extract``, if any.

    ``harness-memory`` degrades instead of raising: the returned dict carries
    ``failure_reason`` when the extraction LLM call failed. Older / foreign
    shapes may expose it as ``error``.
    """
    if not isinstance(result, dict):
        return None
    for key in ("failure_reason", "error"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


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


async def _ensure_memory_service(registry: Any, agent_id: str) -> Any | None:
    """Resolve ``MemoryService``, starting the expert when it is stopped.

    Terminal hooks (Cursor / Claude Code / …) capture into L0 even while the
    expert is unloaded; extraction still needs the agent's configured LLM via
    the live ``MemoryService``. Start failures are logged at WARNING.
    """
    service = _live_memory_service(registry, agent_id)
    if service is not None:
        return service
    start = getattr(registry, "start", None)
    if not callable(start):
        logger.warning(
            "memory extract: agent %s has no MemoryService and registry cannot start",
            agent_id,
        )
        return None
    try:
        await start(agent_id)
    except Exception:
        logger.warning(
            "memory extract: failed to start agent %s for extract",
            agent_id,
            exc_info=True,
        )
        return None
    service = _live_memory_service(registry, agent_id)
    if service is None:
        logger.warning(
            "memory extract: agent %s started but MemoryService still unavailable",
            agent_id,
        )
    return service


def _trigger_extract(server: OctopServer, session_id: str | None) -> bool:
    """Asynchronously extract + promote after MCP ``memory_capture``.

    MCP-written L0 events are outside the harness extractor's tracked sessions,
    so capture must schedule extract explicitly. If the expert is stopped, start
    it first so the in-process ``MemoryService`` (with the agent's extraction
    LLM) can run. Failures are logged at WARNING — never silently skipped.
    Returns whether an extract task was scheduled.
    """
    import asyncio

    agent_id = _current_agent_id.get()
    if not session_id or not agent_id:
        if agent_id and not session_id:
            logger.warning(
                "memory extract skipped for agent %s: capture returned no session_id",
                agent_id,
            )
        return False

    runtime_server = getattr(server, "app_runtime", None)
    if runtime_server is None:
        logger.warning(
            "memory extract skipped for agent %s session %s: app_runtime unavailable",
            agent_id,
            session_id,
        )
        return False
    registry = getattr(runtime_server, "agent_registry", None)
    if registry is None:
        logger.warning(
            "memory extract skipped for agent %s session %s: agent_registry unavailable",
            agent_id,
            session_id,
        )
        return False

    async def _extract() -> None:
        try:
            service = await _ensure_memory_service(registry, agent_id)
            if service is None:
                return
            result = await asyncio.to_thread(
                service.extract,
                session_id,
                incremental=True,
                promote=True,
                regen_pages=True,
            )
        except Exception:
            logger.warning(
                "memory extract failed for agent %s session %s",
                agent_id,
                session_id,
                exc_info=True,
            )
            return
        # ``extract`` reports LLM / promotion failures inside the result
        # instead of raising, so a silently-dead model chain would otherwise
        # leave no trace above INFO. Surface it as a warning.
        reason = _extract_failure_reason(result)
        if reason:
            logger.warning(
                "memory extract failed for agent %s session %s: %s",
                agent_id,
                session_id,
                reason,
            )
            return
        logger.info(
            "memory extract done for agent %s session %s: %s",
            agent_id,
            session_id,
            result,
        )

    try:
        asyncio.create_task(_extract())
        return True
    except Exception:
        logger.warning(
            "memory extract trigger failed for agent %s session %s",
            agent_id,
            session_id,
            exc_info=True,
        )
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


async def _send_text(
    send: Any, status: int, body: str, *, content_type: str = "text/plain; charset=utf-8"
) -> None:
    payload = body.encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", content_type.encode("ascii")),
                (b"content-length", str(len(payload)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


def _instance_config() -> dict[str, Any]:
    """The instance ``config.json`` as a dict (empty when missing/unreadable)."""
    import json  # noqa: PLC0415

    from octop.infra.utils.paths import PathLayout  # noqa: PLC0415

    try:
        raw = PathLayout.from_env().config.read_text(encoding="utf-8")
        loaded = json.loads(raw)
    except Exception:  # noqa: BLE001 - a missing/odd config must not break /setup
        return {}
    return loaded if isinstance(loaded, dict) else {}


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
"""本机地址：只有它没有 TLS 前置，按请求的 scheme 走 http。"""


def _host_without_port(host: str) -> str:
    """``host``（可能带 ``:port`` 或 IPv6 方括号）里的裸主机名，小写。"""
    value = host.strip()
    if value.startswith("["):
        return value[1:].split("]", 1)[0].lower()
    return value.split(":", 1)[0].lower()


def _host_mount_url(scheme: str, host: str) -> str:
    """本实例自己的挂载点（hooks 永远打它）。

    本机照请求 scheme 走 http（没有 TLS 前置）；其余一律 **https** —— 反代/ingress 通常在
    这一层终结 TLS，``http://`` 打不通，而 ``X-Forwarded-Proto`` 不可靠（网关不透传或透传成 http）。
    """
    if _host_without_port(host) in _LOOPBACK_HOSTS:
        return f"{scheme or 'http'}://{host}/mcp/memory/"
    return f"https://{host}/mcp/memory/"


def _default_mcp_url(scheme: str, host: str) -> str:
    """客户端条目默认该连的地址：本实例自己的挂载点。

    ``?url=`` / ``OCTOP_MEMORY_PUBLIC_MCP_URL`` / ``memory_public_mcp_url`` 仍是**显式覆盖**，
    部署可以用它把客户端条目指向自建的公网入口。
    """
    return _host_mount_url(scheme, host)


def _public_mcp_url() -> str | None:
    """**显式覆盖**的客户端条目地址（部署可选）：

    * ``OCTOP_MEMORY_PUBLIC_MCP_URL`` (environment), or
    * ``memory_public_mcp_url`` in the instance's ``config.json``.

    没配也照样能用 —— 默认地址就是本实例自己的挂载点。
    """
    from_env = os.environ.get("OCTOP_MEMORY_PUBLIC_MCP_URL", "").strip()
    if from_env:
        return from_env
    return _config_public_mcp_url()


def _config_public_mcp_url() -> str | None:
    """``memory_public_mcp_url`` from the instance ``config.json`` (None when absent)."""
    value = str(_instance_config().get("memory_public_mcp_url") or "").strip()
    return value or None


class _InstallerApp:
    """ASGI app for ``/setup``: the unauthenticated local-client installer.

    It hands out no credential — the script asks for the token at run time — so it
    deliberately sits outside the memory MCP token check; the only artifact is the
    script. Deleting this route (or the whole mount) removes nothing else.
    """

    def __init__(self, server: OctopServer) -> None:
        self._server = server

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        from urllib.parse import parse_qsl  # noqa: PLC0415

        if scope.get("type") != "http":
            return
        if str(scope.get("method", "GET")).upper() not in ("GET", "HEAD"):
            await _send_text(send, 405, "GET only\n")
            return

        from octop.infra.agents.client_setup import render_setup_script  # noqa: PLC0415

        query = dict(parse_qsl(scope.get("query_string", b"").decode("utf-8")))
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
        }
        scheme = headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
        host = headers.get("host", "127.0.0.1")
        # hooks 走本实例的直连挂载点；mcp_url 是登记进客户端 MCP 条目的地址，缺省就是本实例
        # 的挂载点（部署可用 ?url= / memory_public_mcp_url 指向自建的公网入口）。两份地址共用
        # 同一份实例共享 token。
        instance_url = _host_mount_url(scheme, host)
        script = render_setup_script(
            mcp_url=query.get("url") or _public_mcp_url() or _default_mcp_url(scheme, host),
            hook_url=query.get("hook_url") or instance_url,
            agent_id=(query.get("agent") or "").strip(),
            terminals=(query.get("terminals") or "").strip(),
            # 实例发布时的 OCTOP_MEMORY_MCP_TOKEN 直接内置成脚本默认凭据：用户只需专家 ID
            # （+ 可选用户标识）。注意 /setup 本身不鉴权 —— 谁连得到它就拿到这个 token。
            default_token=_memory_mcp_token() or "",
        )
        await _send_text(send, 200, script, content_type="text/x-shellscript; charset=utf-8")


class _UninstallerApp:
    """ASGI app for ``/uninstall``: counterpart of ``/setup`` (also unauthenticated)."""

    def __init__(self, server: OctopServer) -> None:
        self._server = server

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        from urllib.parse import parse_qsl  # noqa: PLC0415

        if scope.get("type") != "http":
            return
        if str(scope.get("method", "GET")).upper() not in ("GET", "HEAD"):
            await _send_text(send, 405, "GET only\n")
            return

        from octop.infra.agents.client_setup import render_uninstall_script  # noqa: PLC0415

        query = dict(parse_qsl(scope.get("query_string", b"").decode("utf-8")))
        script = render_uninstall_script(terminals=(query.get("terminals") or "").strip())
        await _send_text(send, 200, script, content_type="text/x-shellscript; charset=utf-8")


class _SetupFirstApp:
    """Serve ``<mount>/setup`` and ``/uninstall`` before the token check, then MCP.

    Both scripts hand out no credential, so they sit in front of
    ``_TokenAuthMiddleware``. Keeping them under the same mount means a
    deployment that only exposes ``/mcp…`` needs no extra ingress rule.
    """

    def __init__(self, installer: Any, uninstaller: Any, inner: Any) -> None:
        self._installer = installer
        self._uninstaller = uninstaller
        self._inner = inner

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            path = str(scope.get("path", ""))
            root = str(scope.get("root_path", ""))
            relative = path[len(root) :] if root and path.startswith(root) else path
            cleaned = relative.rstrip("/")
            if cleaned == "/setup":
                await self._installer(scope, receive, send)
                return
            if cleaned == "/uninstall":
                await self._uninstaller(scope, receive, send)
                return
        await self._inner(scope, receive, send)


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
        _SetupFirstApp(
            _InstallerApp(server),
            _UninstallerApp(server),
            _TokenAuthMiddleware(_AgentRouter(streamable_app, server), token),
        ),
    )
    return managers


__all__ = ["build_memory_mcp", "mount_memory_mcp"]
