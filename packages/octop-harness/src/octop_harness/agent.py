"""``HarnessAgent`` — the public facade over ``deepagents.create_deep_agent``."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, cast

import deepagents
from deepagents.middleware.memory import MemoryMiddleware as DeepAgentsMemoryMiddleware
from langchain.agents.middleware import PIIMiddleware

from octop_harness.backends import resolve_backend, spec_supports_execution
from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS
from octop_harness.backends.workspace import DEFAULT_MEMORY_FILES, BackendWorkspace
from octop_harness.builtin.tools import browser_use, web_fetch
from octop_harness.builtin.tools.ask_user import ASK_USER_TOOL_NAME, ask_user_question
from octop_harness.builtin.tools.current_time import CurrentTimeTool
from octop_harness.builtin.tools.desktop_screenshot import build_desktop_screenshot_tool
from octop_harness.builtin.tools.env_file import build_env_file_tools
from octop_harness.builtin.tools.media_generation import build_media_generation_tools
from octop_harness.builtin.tools.send_file import build_send_file_to_user_tool
from octop_harness.builtin.tools.web_search import load_web_search_tools
from octop_harness.config import HarnessAgentConfig
from octop_harness.init import InitResult
from octop_harness.llm.factory import ChatModelFactory
from octop_harness.llm.session_header import session_header_scope
from octop_harness.mcp import load_mcp_tools, mcp_tool_names, validate_mcp_default_servers
from octop_harness.memory import MemoryRuntime
from octop_harness.middleware.bootstrap import BootstrapMiddleware, bootstrap_marker_exists
from octop_harness.middleware.checkpoint_ts import CheckpointTsMiddleware
from octop_harness.middleware.context_usage import ContextUsageMiddleware
from octop_harness.middleware.mcp_tools import MCPToolMiddleware
from octop_harness.middleware.media_offload import MediaOffloadMiddleware
from octop_harness.middleware.model_retry import ModelRetryMiddleware
from octop_harness.middleware.model_router import ModelRouterMiddleware
from octop_harness.middleware.model_settings import ModelSettingsMiddleware
from octop_harness.middleware.pii import detect_pii
from octop_harness.middleware.session_header import SessionHeaderMiddleware
from octop_harness.middleware.skill_filter import SkillFilterMiddleware, render_slash_skill_prompt
from octop_harness.middleware.tool_order import TaskToolLastMiddleware
from octop_harness.middleware.tool_search import ToolSearchMiddleware
from octop_harness.middleware.tools_filter import ToolsFilterMiddleware
from octop_harness.protocols import resolve_protocol
from octop_harness.request import ChatRequest

# ``langgraph-checkpoint-sqlite`` is a declared dependency, but we still guard
# the import so missing wheels surface as a single warning at construction
# rather than an ImportError at module load. We default to the *async* saver
# because all invocation paths (``call`` / ``stream`` / ``aget_history``) are
# async — a sync ``SqliteSaver`` raises ``NotImplementedError`` under
# ``astream``.
try:
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver as _AsyncSqliteSaver
except ImportError:  # pragma: no cover - dependency is listed; defensive
    aiosqlite = None  # type: ignore[assignment]
    _AsyncSqliteSaver = None  # type: ignore[assignment, misc]

if TYPE_CHECKING:
    from deepagents.backends.protocol import BackendProtocol
    from langchain_core.messages import BaseMessage

    from octop_harness.context_usage import ContextUsage
    from octop_harness.protocols.base import ChatProtocol
    from octop_harness.teams.team_manager import TeamManager

logger = logging.getLogger(__name__)


def _tool_name_of(tool: Any) -> str:
    """Best-effort tool name for heterogeneous tool objects (never raises)."""
    name = getattr(tool, "name", None)
    if isinstance(name, str):
        return name
    if isinstance(tool, dict):
        raw = tool.get("name")
        if isinstance(raw, str):
            return raw
    return ""


class HarnessAgent:
    """A production-ready agent built on ``deepagents.create_deep_agent``.

    This class is intentionally a *thin* facade: it composes the harness
    defaults (backend, session logger, model router, built-in skills, etc.)
    into a single ``CompiledStateGraph`` and exposes a small ergonomic
    surface (``call`` / ``stream`` / ``stream_events``).

    Direct access to the underlying graph is preserved via :py:attr:`graph`
    and :py:attr:`backend` for users who need to plug into deep-agent's
    full feature set.

    Path model
    ----------
    ``config.workspace_dir`` is the agent's **recommended working directory**
    (absolute). It is a different dimension from backend ``root_dir`` (a
    construction-time mount for virtual ``/``). Callers may pass either a
    host path or an agent-facing rootfs path (e.g. ``/.octop/workspaces/<id>``);
    harness maps the latter onto ``{root_dir}/…`` for local persistence only.

    * **Backend** — when ``config.backend`` is ``local_shell`` / ``filesystem``
      and the spec doesn't pin its own ``root_dir``, we fall back to the
      on-disk workspace so virtual ``/`` lines up with the workspace on disk.
      Local backends resolved with a workspace are wrapped so deepagents
      conversation history / media offloads use
      ``{workspace}/{system_files_path}`` as ``artifacts_root`` (Octop:
      ``.octop``), independent of ``root_dir``.
    * **Local runtime persistence** — memory databases, ``sessions/``
      (JSONL), and ``checkpoints.sqlite`` are written under the on-disk
      workspace directly (real OS fds / database drivers; not via
      ``BackendWorkspace``). Runtime diagnostic logs are process-wide
      (default ``~/.octop-harness/logs``), configured on
      :class:`~octop_harness.manager.HarnessAgentManager` or
      :func:`~octop_harness.observability.logging.setup_logging`.
    * **L1 agent content** — harness reads/writes agent-visible / agent-used
      workspace content only through
      :class:`~octop_harness.backends.workspace.BackendWorkspace`
      (``agent.workspace``), including materialize failback under
      ``virtual_mode``. This does not include the local runtime persistence
      listed above.
    * **Backend artifacts** — seeded markdown / skills live at the backend's
      ``/`` when that mount is aligned with the workspace.

    Lifecycle
    ---------
    The instance owns long-lived resources (notably a SqliteSaver context
    manager when the default checkpointer is used). Either call
    :py:meth:`close` explicitly or use the agent as a context manager::

        with HarnessAgent(cfg) as agent:
            await agent.call("hello")
    """

    _mcp_tools: list[Any]
    _mcp_tool_name_set: frozenset[str]

    def __init__(
        self,
        config: HarnessAgentConfig,
        *,
        model_factory: ChatModelFactory | None = None,
        team_manager: TeamManager | None = None,
        agent_id: str | None = None,
    ) -> None:
        self._config = config
        self._team_manager = team_manager
        self._agent_id = agent_id

        self._init_paths()
        # Map agent-facing workspace → host path before backend resolve so
        # local backends receive a real on-disk workspace_dir.
        self._workspace_path = self._host_workspace_path()
        self._init_logging()
        self._init_mcp()

        self._backend = self._build_backend()
        # Re-map once the live backend is available (instance mounts).
        self._workspace_path = self._host_workspace_path()
        self._workspace = BackendWorkspace(
            self._backend,
            self._workspace_path,
            system_files_path=self._config.system_files_path,
        )
        self._wire_workspace_dotenv_for_execute()
        self._owns_model_factory = model_factory is None
        self._model_factory = self._init_model_factory(model_factory)
        self._memory_runtime = MemoryRuntime(
            config=config,
            workspace_path=self._workspace_path,
            model_factory=self._model_factory,
            workspace=self._workspace,
        )
        self._langfuse_callbacks: list[Any] | None = None
        self._protocols: dict[str, ChatProtocol] = {}
        # Optional hook called once immediately after bootstrap completes.
        # Set by the caller (e.g. Orca) to trigger a full config reload.
        self.on_bootstrap_complete: Callable[[], None] | None = None
        self._context_usage_mw: ContextUsageMiddleware | None = None
        self._summarization_mw: Any | None = None

        self._init_graph()
        self._init_protocols()
        self._model_factory.bind_runtime(
            get_protocol=self._get_protocol,
            agent_config=self._config,
        )
        self._bind_plugin_model_factory()
        self._thread_models: dict[str, str] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        # Guards the resources released by close() against a host that
        # hot-reloads while an invocation is still running. Locked rather than
        # loop-local because close() may arrive from a worker thread.
        self._lifecycle_lock = threading.Lock()
        self._in_flight = 0
        self._close_pending = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def config(self) -> HarnessAgentConfig:
        return self._config

    @property
    def agent_id(self) -> str | None:
        """Registry id from ``HarnessAgentManager``; ``None`` if constructed directly."""
        return self._agent_id

    @property
    def graph(self) -> Any:
        """The underlying deep-agent ``CompiledStateGraph`` (escape hatch)."""
        return self._graph

    @property
    def backend(self) -> BackendProtocol:
        """The underlying backend instance (escape hatch)."""
        return self._backend

    @property
    def workspace(self) -> BackendWorkspace:
        """Facade for L1 agent storage reads/writes via the backend."""
        return self._workspace

    @property
    def memory(self) -> Any | None:
        """Low-level structured memory instance for advanced inspection/debugging."""
        return self._memory_runtime.memory

    def memory_maintenance_status(self) -> dict[str, Any] | None:
        """Slimming phase for host status APIs. ``None`` when memory is off."""
        middleware = self._memory_runtime.middleware
        if middleware is None:
            return None
        return middleware.maintenance_status()

    @property
    def checkpointer(self) -> Any:
        """The langgraph checkpointer instance for session queries.

        Returns the resolved checkpointer (e.g. SqliteSaver), ``False``
        if explicitly disabled, or ``None`` if unavailable.
        """
        return self._checkpointer_instance

    @property
    def protocol(self) -> ChatProtocol:
        """Current default protocol instance."""
        return self._protocol

    @property
    def model_factory(self) -> ChatModelFactory:
        """The underlying model factory — escape hatch for direct LLM access.

        Example::

        llm = agent.model_factory.get_chat_model("openai/gpt-4o")
        """
        return self._model_factory

    def is_bootstrapped(self) -> bool:
        """True when onboarding completed (marker on backend) or bootstrap is disabled."""
        if not self._config.bootstrap_enabled:
            return True
        return bootstrap_marker_exists(
            self._workspace,
            bootstrap_marker=self._config.bootstrap_marker,
        )

    def append_mcp_tools(self, extra_tools: list[Any]) -> None:
        """Append in-process MCP tools (deduped by name) and recompile the agent graph."""
        if not extra_tools:
            return
        existing = mcp_tool_names(self._mcp_tools)
        new_tools = [tool for tool in extra_tools if getattr(tool, "name", None) not in existing]
        if not new_tools:
            return
        self._mcp_tools = list(new_tools) + list(self._mcp_tools)
        self._mcp_tool_name_set = mcp_tool_names(self._mcp_tools)
        self._init_graph()

    def replace_mcp_tools(self, tools: list[Any]) -> None:
        """Replace in-process MCP tools and recompile the agent graph."""
        self._mcp_tools = list(tools)
        self._mcp_tool_name_set = mcp_tool_names(self._mcp_tools)
        self._init_graph()

    def inject_mcp_tools(self, extra_tools: list[Any]) -> None:
        """Alias for :meth:`append_mcp_tools` (Orca gateway in-process MCP injection)."""
        self.append_mcp_tools(extra_tools)

    def init_workspace(
        self,
        *,
        include_md_files: bool = True,
        include_skills: bool = True,
        include_agents: bool = True,
        overwrite: bool = False,
    ) -> InitResult:
        """Seed the workspace with built-in templates and skills via backend.

        Idempotent: a second call leaves existing files alone unless
        ``overwrite=True``.

        Call this after construction to bootstrap a fresh workspace.
        Templates (``AGENTS.md``, ``BOOTSTRAP.md``, …), built-in skills,
        and built-in subagent markdown are written under ``workspace_dir``
        via :class:`BackendWorkspace`.
        """
        return self._workspace.init_workspace(
            language=self._config.language,
            include_md_files=include_md_files,
            include_skills=include_skills,
            include_agents=include_agents,
            overwrite=overwrite,
        )

    def get_protocol(self, name: str) -> ChatProtocol:
        """Get a protocol instance by name (cached).

        For HTTP integration::

            agent.get_protocol("openai").create_chat_completion(body)
        """
        return self._get_protocol(name)

    def set_skills_disabled(
        self,
        disabled: frozenset[str] | set[str] | list[str] | None,
    ) -> None:
        """Hot-update disabled skills (slug or display name) without recompiling the graph.

        Removes disabled skills from the system prompt and blocks filesystem
        / ``execute`` access to their ``skills/<slug>`` trees via
        ``SkillFilterMiddleware``.
        """
        self._config.skills_disabled = frozenset(str(x) for x in (disabled or ()))

    def set_tools_disabled(
        self,
        disabled: frozenset[str] | set[str] | list[str] | None,
    ) -> None:
        """Hot-update disabled tool names without recompiling the graph.

        ``ToolsFilterMiddleware`` strips matching names from each
        ``ModelRequest.tools`` list before the LLM call.
        """
        self._config.tools_disabled = frozenset(str(x) for x in (disabled or ()))

    def reload_subagents(self) -> None:
        """Rescan workspace agent markdown and recompile the agent graph."""
        self._init_graph()

    async def list_skill_summaries(self) -> list[dict[str, Any]]:
        """Installed skills for this agent (builtin + workspace + ``skills_dir``)."""
        from octop_harness.skills.catalog import list_skill_summaries as _list_skill_summaries

        return await _list_skill_summaries(
            self._workspace,
            skills_disabled=self._config.skills_disabled,
            skills_dir=self._config.skills_dir,
        )

    async def list_subagent_summaries(self) -> list[dict[str, Any]]:
        """Installed subagents from workspace ``agents/**/*.md`` manifests."""
        from octop_harness.subagents.catalog import list_subagent_summaries as _list_subagent_summaries

        return await _list_subagent_summaries(
            self._workspace,
            subagents_path=self._config.subagents_path,
        )

    # ----- Invocation -----

    def cancel(self, thread_id: str) -> None:
        """Signal an in-flight :meth:`stream` for *thread_id* to stop."""
        if event := self._cancel_events.get(thread_id):
            event.set()

    def get_thread_model(self, thread_id: str) -> str | None:
        return self._thread_models.get(thread_id)

    def set_thread_model(self, thread_id: str, model: str) -> None:
        self._thread_models[thread_id] = model

    def clear_thread_model(self, thread_id: str) -> None:
        self._thread_models.pop(thread_id, None)

    async def _iter_until_cancelled(
        self,
        source: AsyncIterator[Any],
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[Any]:
        """Yield from *source* until *cancel_event* is set.

        Unlike a plain ``async for`` + flag check between chunks, this preempts a
        blocked ``__anext__`` (LLM/tool await) so cancel is not stuck until the
        next token.
        """
        it = source.__aiter__()
        try:
            while not cancel_event.is_set():
                next_task: asyncio.Task[Any] = asyncio.create_task(cast("Coroutine[Any, Any, Any]", it.__anext__()))
                cancel_task = asyncio.create_task(cancel_event.wait())
                try:
                    _done, _pending = await asyncio.wait(
                        {next_task, cancel_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                except BaseException:
                    next_task.cancel()
                    cancel_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await next_task
                    with contextlib.suppress(asyncio.CancelledError):
                        await cancel_task
                    raise

                if cancel_event.is_set():
                    next_task.cancel()
                    with contextlib.suppress(
                        asyncio.CancelledError,
                        StopAsyncIteration,
                        Exception,
                    ):
                        await next_task
                    cancel_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await cancel_task
                    return

                cancel_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await cancel_task
                try:
                    yield next_task.result()
                except StopAsyncIteration:
                    return
        finally:
            close = getattr(it, "aclose", None)
            if close is not None:
                with contextlib.suppress(Exception):
                    await close()

    async def call(
        self,
        request: ChatRequest | str | dict[str, Any],
        *,
        protocol: str | None = None,
    ) -> dict[str, Any]:
        """Non-streaming invocation. Output format determined by protocol."""
        from octop_harness.slash.runtime import build_runtime_ctx, call_with_runtime_slash

        req = ChatRequest.coerce(request)
        ctx = build_runtime_ctx(self, req)

        async def _call(prepared: ChatRequest) -> dict[str, Any]:
            messages, config, proto = self._prepare_call(prepared, protocol)
            with session_header_scope(prepared.thread_id):
                return await proto.call(messages, config)

        from octop_harness.observability.logging import logging_scope

        async with self._invocation():
            with logging_scope(self._agent_id):
                return await call_with_runtime_slash(req, ctx=ctx, call=_call)

    async def stream(
        self,
        request: ChatRequest | str | dict[str, Any],
        *,
        protocol: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        """Stream protocol-formatted chunks from the graph.

        Yields dict chunks in the protocol's native format:
        - langgraph: ``{"type": "token", "content": "...", "node": "..."}``
        - openai: ChatCompletionChunk dicts
        - mcp: MCP SamplingMessage dicts
        """
        from octop_harness.slash.runtime import build_runtime_ctx, iter_with_runtime_slash

        req = ChatRequest.coerce(request)
        ctx = build_runtime_ctx(self, req)

        async def _stream(prepared: ChatRequest) -> AsyncIterator[Any]:
            messages, config, proto = self._prepare_call(prepared, protocol)
            thread_id = prepared.thread_id or ""
            cancel_event = asyncio.Event()
            if thread_id:
                self._cancel_events[thread_id] = cancel_event
            try:
                with session_header_scope(prepared.thread_id):
                    async for chunk in self._iter_until_cancelled(
                        proto.stream(messages, config, **kwargs),
                        cancel_event,
                    ):
                        yield chunk
            finally:
                if thread_id:
                    self._cancel_events.pop(thread_id, None)

        from octop_harness.observability.logging import logging_scope

        chunks = iter_with_runtime_slash(req, ctx=ctx, stream=_stream).__aiter__()
        async with self._invocation():
            try:
                while True:
                    with logging_scope(self._agent_id):
                        try:
                            chunk = await chunks.__anext__()
                        except StopAsyncIteration:
                            return
                    yield chunk
            finally:
                close = getattr(chunks, "aclose", None)
                if close is not None:
                    with logging_scope(self._agent_id):
                        await close()

    async def resume_hitl(
        self,
        thread_id: str,
        decisions: list[dict[str, Any]],
        *,
        protocol: str | None = None,
    ) -> AsyncIterator[Any]:
        """Resume a paused human-in-the-loop interrupt for *thread_id*."""
        proto = self._get_protocol(protocol)
        resume_stream = getattr(proto, "resume_stream", None)
        if resume_stream is None:
            msg = f"Protocol {proto.name!r} does not support HITL resume"
            raise ValueError(msg)
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        async with self._invocation():
            with session_header_scope(thread_id):
                async for chunk in resume_stream(thread_id, decisions, config):
                    yield chunk

    async def stream_events(
        self,
        request: ChatRequest | str | dict[str, Any],
        *,
        protocol: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Return a v3 stream object for structured event consumption.

        The returned stream provides typed projections:
        - stream.messages — text, reasoning, tool_calls per LLM call
        - stream.values — state snapshots
        - stream.output — final state
        - stream.subgraphs — nested graph runs

        Note: Unlike ``call`` and ``stream``, this method does **not** pass
        through ``iter_with_runtime_slash``, so runtime slash commands (e.g.
        ``/reset``) are **not** intercepted.  Callers that need slash handling
        should use ``stream`` instead, or pre-process the input themselves.
        """
        messages, config, proto = self._prepare_call(request, protocol)
        return await proto.stream_events(messages, config, **kwargs)

    async def aget_history(
        self,
        thread_id: str,
        *,
        limit: int = 50,
        before: str | None = None,
    ) -> list[BaseMessage]:
        """Return the chat history for *thread_id* from the checkpointer.

        Parameters
        ----------
        thread_id:
            The conversation thread to query (same value used in
            :py:class:`~octop_harness.request.ChatRequest`).
        limit:
            Maximum number of messages to return. The *most recent* ``limit``
            messages are returned in chronological order (oldest first).
            Defaults to 50.
        before:
            Optional checkpoint_id cursor. When set, only messages from
            checkpoints created **before** that checkpoint are considered.
            Useful for cursor-based pagination: pass the checkpoint_id of the
            oldest message in the previous page.

        Returns
        -------
        list[BaseMessage]
            Messages in chronological order (oldest first).  Returns ``[]``
            when the checkpointer is unavailable or the thread has no history.

        Notes
        -----
        Prefers a single newest-checkpoint read (``alist`` / ``list``,
        ``limit=1``). That is one ``checkpoints`` row for the default SQLite
        saver — no multi-table scan.

        Delta-channel checkpointers (e.g. ``octop-memory``) may leave
        ``channel_values["messages"]`` empty on the latest checkpoint even
        when the thread has history. Only then does this method call
        ``graph.aget_state`` to reconstruct the merged transcript.

        Messages stamped by
        :class:`~octop_harness.middleware.checkpoint_ts.CheckpointTsMiddleware`
        carry ``additional_kwargs["checkpoint_ts"]`` (wall-clock epoch ms).
        Older messages written before that middleware simply omit the key —
        this method does not backfill timestamps.
        """
        from langchain_core.messages import BaseMessage  # runtime import: needed for isinstance() check

        cp = self._checkpointer_instance
        if not cp:
            logger.warning(
                "aget_history: checkpointer unavailable; returning empty history for thread %r",
                thread_id,
            )
            return []

        before_config: dict[str, Any] | None = (
            {"configurable": {"checkpoint_id": before}} if before is not None else None
        )
        raw = await self._read_history_checkpoint(
            cp,
            config={"configurable": {"thread_id": thread_id}},
            before_config=before_config,
        )
        if raw is not None:
            base_messages = [m for m in raw if isinstance(m, BaseMessage)]
            if base_messages:
                return base_messages[-limit:]

        # Empty / missing messages on the latest checkpoint (delta savers), or
        # checkpointer read failed — reconstruct via graph state.
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        if before is not None:
            config["configurable"]["checkpoint_id"] = before
        base_messages = await self._read_history_from_graph_state(config)
        return base_messages[-limit:] if base_messages else []

    async def aappend_messages(
        self,
        thread_id: str,
        messages: Sequence[BaseMessage],
    ) -> list[BaseMessage]:
        """Append canonical messages to a thread without invoking the model.

        Messages are persisted through LangGraph's ``messages`` reducer so the
        next model turn sees them. Existing IDs are preserved for idempotent
        retries; missing IDs and checkpoint timestamps are filled before the
        atomic state update.
        """
        from langchain_core.messages import BaseMessage

        from octop_harness.middleware.checkpoint_ts import stamp_missing_checkpoint_ts

        tid = thread_id.strip()
        if not tid:
            raise ValueError("thread_id must not be empty")
        if not messages:
            raise ValueError("messages must not be empty")
        if not self._checkpointer_instance:
            raise RuntimeError("cannot append messages without a checkpointer")

        now_ms = int(time.time() * 1000)
        prepared: list[BaseMessage] = []
        for message in messages:
            if not isinstance(message, BaseMessage):
                raise TypeError("messages must contain only BaseMessage instances")
            with_id = message if message.id else message.model_copy(update={"id": uuid.uuid4().hex})
            stamped = stamp_missing_checkpoint_ts([with_id], now_ms=now_ms)
            prepared.append(stamped[0] if stamped else with_id)

        await self._graph.aupdate_state(
            {"configurable": {"thread_id": tid}},
            {"messages": prepared},
        )
        return prepared

    async def adelete_thread(self, thread_id: str) -> bool:
        """Delete all checkpoint data for *thread_id* from the underlying checkpointer.

        This removes the conversation's actual state (messages, tool
        results, everything the graph persisted) — not just whatever
        UI-level bookkeeping a host (e.g. Octop's thread list) keeps
        alongside it. Hosts that track their own thread metadata should
        call this *before* deleting their own row, so a failure here
        still leaves the thread visible/retryable instead of losing the
        only handle to data that didn't actually get deleted.

        Returns
        -------
        bool
            ``True`` when checkpoint data was deleted. ``False`` when no
            checkpointer is configured — there is nothing to delete, which
            is a normal/expected state (e.g. ``checkpointer=False``), not
            an error.

        Raises
        ------
        NotImplementedError
            The checkpointer is configured but its saver doesn't support
            thread deletion. Raised rather than swallowed: silently
            keeping data the caller asked to delete is not an acceptable
            fallback for a privacy/retention operation.
        """
        cp = self._checkpointer_instance
        if not cp:
            logger.warning(
                "adelete_thread: checkpointer unavailable; no checkpoint data to delete for thread %r",
                thread_id,
            )
            return False
        if hasattr(cp, "adelete_thread"):
            await cp.adelete_thread(thread_id)
        elif hasattr(cp, "delete_thread"):
            await asyncio.to_thread(cp.delete_thread, thread_id)
        else:
            raise NotImplementedError(f"checkpointer {type(cp).__name__!r} does not support thread deletion")
        return True

    async def aget_context_usage(
        self,
        thread_id: str,
        *,
        max_tokens: int | None = None,
    ) -> ContextUsage:
        """Return context-window usage for *thread_id*.

        Prefers the in-process snapshot written by
        :class:`~octop_harness.middleware.context_usage.ContextUsageMiddleware`.
        On a miss, loads only the latest checkpoint transcript and reads
        ``additional_kwargs["context_usage"]`` from the newest AI message —
        it does not scan full history pages.
        """
        from octop_harness.context_usage import empty_context_usage
        from octop_harness.middleware.context_usage import resolve_context_usage

        cap = max_tokens
        mw = self._context_usage_mw
        if mw is not None:
            snap = mw.get_snapshot(thread_id)
            if snap is not None and snap.source != "empty":
                return snap if cap is None else snap.with_max_tokens(cap)

        messages = await self.aget_history(thread_id, limit=40)
        fallback_cap = cap if cap is not None else self._default_max_input_tokens()
        if not messages:
            return empty_context_usage(max_tokens=fallback_cap)
        resolved = resolve_context_usage(
            thread_id=thread_id,
            middleware=None,
            messages=messages,
            max_tokens=cap,
        )
        if resolved.source == "empty" and cap is None:
            return empty_context_usage(max_tokens=fallback_cap)
        return resolved

    async def acompact_conversation(
        self,
        thread_id: str,
        *,
        model: str | None = None,
    ) -> Any:
        """Force one SummarizationMiddleware cycle: offload history + write summary.

        Ignores the auto 85% token trigger. Uses a tighter keep policy than
        auto-compaction (last few messages) so ``/compact`` visibly shrinks
        model context. The summary LLM follows *model* when provided.
        Does **not** create a new thread.
        """
        from octop_harness.compaction import CompactResult, force_compact_thread

        if not thread_id:
            return CompactResult(ok=False, reason="unavailable", error="missing thread_id")
        graph = getattr(self, "_graph", None) or getattr(self, "_base_graph", None)
        if graph is None:
            return CompactResult(ok=False, reason="unavailable", error="graph not ready")

        model_ref = (model or "").strip() or None
        if model_ref:
            try:
                chat_model = self._model_factory.get_chat_model(model_ref)
            except DEFENSIVE_OP_ERRORS:
                chat_model = self._build_seed_model()
        else:
            chat_model = self._build_seed_model()

        result = await force_compact_thread(
            graph=graph,
            backend=self._backend,
            model=chat_model,
            thread_id=thread_id,
            model_ref=model_ref,
            summarization_middleware=self._summarization_mw,
        )
        # No model call happened, so ContextUsageMiddleware wrote no new
        # snapshot — and its in-process snapshot outranks the message stamp in
        # ``aget_context_usage``. Without this the host context ring keeps
        # reporting the pre-compaction total until the next turn.
        if result.ok and self._context_usage_mw is not None:
            self._context_usage_mw.shrink_snapshot(thread_id, removed_tokens=result.removed_tokens)
        return result

    def _default_max_input_tokens(self) -> int:
        from octop_harness.context_usage import DEFAULT_MAX_TOKENS

        ref = self._config.pick_default_model_ref()
        try:
            provider_id, _, model_id = ref.partition("/")
            if not model_id:
                provider_id, model_id = "", ref
            for provider in self._config.providers:
                if provider.id != provider_id and provider_id:
                    continue
                model = provider.get_model(model_id)
                if model is not None and model.max_input_tokens > 0:
                    return int(model.max_input_tokens)
        except DEFENSIVE_OP_ERRORS:
            logger.debug("resolve max_input_tokens failed for %r", ref, exc_info=True)
        return DEFAULT_MAX_TOKENS

    async def _read_history_from_graph_state(self, config: dict[str, Any]) -> list[BaseMessage]:
        """Reconstruct messages when the latest checkpoint omits ``messages``.

        With delta-channel checkpointers (notably ``octop-memory``), the
        newest checkpoint's ``channel_values`` often stores only auxiliary
        channels while ``messages`` are accumulated via pending writes.
        ``CompiledStateGraph.aget_state`` applies those writes and returns
        the merged transcript.
        """
        from langchain_core.messages import BaseMessage  # runtime import: isinstance() check

        thread_id = config.get("configurable", {}).get("thread_id")
        try:
            state = await self._graph.aget_state(config)
        except DEFENSIVE_OP_ERRORS:
            logger.warning(
                "aget_history: graph.aget_state failed for thread %r",
                thread_id,
                exc_info=True,
            )
            return []
        raw = (state.values or {}).get("messages") if state is not None else None
        if not isinstance(raw, list):
            return []
        return [m for m in raw if isinstance(m, BaseMessage)]

    async def _read_history_checkpoint(
        self,
        cp: Any,
        *,
        config: dict[str, Any],
        before_config: dict[str, Any] | None,
    ) -> list[Any] | None:
        """Read the newest checkpoint's message list from sync or async savers.

        Returns ``[]`` when the row exists but ``messages`` is absent/empty,
        and ``None`` when the checkpointer cannot be read at all.
        """
        if hasattr(cp, "alist"):
            try:
                async for checkpoint_tuple in cp.alist(config, before=before_config, limit=1):
                    messages = checkpoint_tuple.checkpoint.get("channel_values", {}).get("messages", [])
                    return messages if isinstance(messages, list) else []
                return []
            except NotImplementedError:
                # octop-memory uses sync SqliteSaver; fall through to list().
                pass
            except DEFENSIVE_OP_ERRORS:
                logger.warning(
                    "aget_history: error reading checkpointer for thread %r",
                    config.get("configurable", {}).get("thread_id"),
                    exc_info=True,
                )
                return None

        if hasattr(cp, "list"):
            try:
                return await asyncio.to_thread(
                    self._sync_list_checkpoint_messages,
                    cp,
                    config,
                    before_config,
                )
            except DEFENSIVE_OP_ERRORS:
                logger.warning(
                    "aget_history: error reading sync checkpointer for thread %r",
                    config.get("configurable", {}).get("thread_id"),
                    exc_info=True,
                )
                return None

        logger.warning(
            "aget_history: checkpointer does not support alist() or list(); returning empty history for thread %r",
            config.get("configurable", {}).get("thread_id"),
        )
        return None

    @staticmethod
    def _sync_list_checkpoint_messages(
        cp: Any,
        config: dict[str, Any],
        before_config: dict[str, Any] | None,
    ) -> list[Any]:
        for checkpoint_tuple in cp.list(config, before=before_config, limit=1):
            messages = checkpoint_tuple.checkpoint.get("channel_values", {}).get("messages", [])
            return messages if isinstance(messages, list) else []
        return []

    # ----- Lifecycle -----

    def end_session(
        self,
        session_id: str,
        *,
        background: bool = True,
    ) -> None:
        """Trigger memory distillation for a finished session.

        Calls :meth:`MemoryService.extract` through the memory middleware to
        promote L0 raw events into L2 atoms (and L3 entity pages) when
        ``memory_extract_on_session_end`` is on. No-op when memory is
        disabled or no service is wired.

        ``background=True`` (the default) returns immediately; pass
        ``False`` for synchronous batch jobs / tests.
        """
        self._memory_runtime.end_session(session_id, background=background)

    @asynccontextmanager
    async def _invocation(self) -> AsyncIterator[None]:
        """Mark this runtime busy so a concurrent :meth:`close` waits for us.

        Hosts hot-reload an agent by dropping their reference and closing it
        (new MCP servers, refreshed connector credentials, a changed provider).
        Closing releases the memory backend and the LangGraph checkpointer
        pool, which a turn already in progress still needs when it flushes its
        writes at the end — otherwise that flush fails on a dead pool
        (``psycopg_pool.PoolClosed``) after the answer was already streamed.
        """
        with self._lifecycle_lock:
            self._in_flight += 1
        try:
            yield
        finally:
            with self._lifecycle_lock:
                self._in_flight -= 1
                release = self._in_flight <= 0 and self._close_pending
                if release:
                    self._close_pending = False
            if release:
                logger.info("releasing deferred close: last invocation finished")
                await self.aclose()

    def _defer_close_while_busy(self) -> bool:
        """Park a close request while invocations still need these resources."""
        with self._lifecycle_lock:
            pending = self._in_flight
            if pending <= 0:
                return False
            self._close_pending = True
        logger.info(
            "close deferred: %d invocation(s) in flight; releasing when the last finishes",
            pending,
        )
        return True

    def close(self) -> None:
        """Release long-lived resources (idempotent, sync).

        Closes the memory SQLite backend and the AsyncSqliteSaver connection
        opened in :py:meth:`_resolve_checkpointer` so underlying file handles
        are released. Also closes the backend when it exposes ``close``
        (e.g. :class:`~octop_harness.backends.docker_sandbox.DockerSandbox`
        detaches its wrapper; persistent Docker containers are not removed).
        Safe to call more than once.

        When tearing down inside a running event loop, prefer :meth:`aclose` so
        ``aiosqlite`` is closed via ``await`` instead of the sync escape hatch.

        While ``call`` / ``stream`` / ``resume_hitl`` is in flight the release is
        deferred and performed once the last one finishes, so a hot-reload
        cannot pull the checkpointer out from under a running turn.
        """
        if self._defer_close_while_busy():
            return
        if self._owns_model_factory:
            self._model_factory.close()
        self._memory_runtime.close()
        self._release_checkpointer()
        self._close_backend()

    async def aclose(self) -> None:
        """Release long-lived resources (idempotent, async).

        Same resources as :meth:`close`, but awaits ``aiosqlite.Connection.close()``
        when a default AsyncSqliteSaver checkpointer is open. Use from ``async
        with`` blocks or other async shutdown paths.

        Deferred while an invocation is in flight, exactly like :meth:`close`.
        """
        if self._defer_close_while_busy():
            return
        if self._owns_model_factory:
            await self._model_factory.aclose()
        self._memory_runtime.close()
        await self._release_checkpointer_async()
        self._close_backend()

    def __del__(self) -> None:
        with contextlib.suppress(Exception):  # pragma: no cover - destructor must not raise
            self.close()

    def __enter__(self) -> HarnessAgent:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    async def __aenter__(self) -> HarnessAgent:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Internal: construction
    # ------------------------------------------------------------------

    def _init_paths(self) -> None:
        """Snapshot the configured workspace path (agent-facing or host).

        ``config.workspace_dir`` is guaranteed absolute by
        ``HarnessAgentConfig.__post_init__``. Host mapping for local
        persistence happens in :meth:`_host_workspace_path` after the
        backend is built (needs ``root_dir`` / ``virtual_mode``).
        """
        self._workspace_path = Path(self._config.workspace_dir)

    @staticmethod
    def _resolve_mount_root(root_raw: object, virtual: bool) -> tuple[Path | None, bool]:
        if root_raw is None:
            return None, virtual
        try:
            return Path(str(root_raw)).expanduser().resolve(), virtual
        except OSError:
            return None, virtual

    def _peek_backend_mount(self) -> tuple[Path | None, bool]:
        """Return ``(root_dir, virtual_mode)`` from the built backend or config spec."""
        backend = getattr(self, "_backend", None)
        if backend is not None:
            virtual = bool(getattr(backend, "virtual_mode", False))
            root_raw = getattr(backend, "root_dir", None) or getattr(backend, "cwd", None)
            if root_raw is None:
                default = getattr(backend, "default", None)
                if default is not None:
                    virtual = virtual or bool(getattr(default, "virtual_mode", False))
                    root_raw = getattr(default, "root_dir", None) or getattr(default, "cwd", None)
            return self._resolve_mount_root(root_raw, virtual)

        spec = self._config.backend
        if not isinstance(spec, dict):
            return None, False
        kind = str(spec.get("type") or "").lower()
        target: dict[str, Any] = spec
        if kind == "composite":
            default = spec.get("default")
            target = default if isinstance(default, dict) else {}
            kind = str(target.get("type") or "").lower()
        if kind not in {"local_shell", "filesystem"}:
            return None, False
        raw = target.get("root_dir")
        virtual = bool(target.get("virtual_mode", True))
        if raw is None or not str(raw).strip():
            return None, virtual
        return self._resolve_mount_root(raw, virtual)

    def _host_workspace_path(self) -> Path:
        """On-disk path for sessions / memory / ``BackendWorkspace``.

        ``config.workspace_dir`` may be an agent-facing rootfs path
        (e.g. ``/.octop/workspaces/<id>``). That value is independent of
        ``root_dir``; when the backend mounts a scoped rootfs we map the
        rootfs path onto ``{root_dir}/…`` for real OS I/O only.
        """
        configured = Path(self._config.workspace_dir).expanduser()
        text = configured.as_posix().replace("\\", "/").strip()
        root, virtual = self._peek_backend_mount()
        if not virtual or root is None:
            return configured.resolve()
        try:
            if root == Path("/").resolve():
                return configured.resolve()
        except OSError:
            return configured.resolve()

        # Agent-facing form under Octop scoped defaults (and ``/`` alone).
        if text == "/" or text.startswith(("/.octop/", "/.agentbuddy/")):
            rel = text.lstrip("/")
            return (root / rel).resolve() if rel else root

        try:
            host = configured.resolve()
        except OSError:
            host = configured
        try:
            host.relative_to(root)
            return host
        except ValueError:
            return host

    def _agent_visible_workspace_dir(self) -> Path:
        """Working directory string shown to the model / tools guidance.

        Prefer the configured ``workspace_dir`` (what the host persisted /
        passed). When that is already a host path under a scoped virtual
        ``root_dir``, present it as a rootfs-absolute path so it matches
        the virtual ``/`` file tools use.
        """
        configured = Path(self._config.workspace_dir)
        text = configured.as_posix().replace("\\", "/").strip()
        if text == "/" or text.startswith(("/.octop/", "/.agentbuddy/")):
            return Path("/") if text == "/" else Path(text)

        ws = self._workspace_path.expanduser().resolve()
        root, virtual = self._peek_backend_mount()
        if not virtual or root is None:
            from octop_harness.backends.workspace import (
                is_cloud_storage_backend,
                remote_workspace_virtual_root,
            )

            backend = getattr(self, "_backend", None)
            if backend is not None and is_cloud_storage_backend(backend):
                ws = Path(remote_workspace_virtual_root(ws))
            return ws
        try:
            if root == Path("/").resolve():
                return ws
            rel = ws.relative_to(root)
        except (OSError, ValueError):
            return ws
        posix = rel.as_posix()
        return Path("/") if not posix or posix == "." else Path("/" + posix)

    def _host_system_dir(self) -> Path:
        """Host directory for sessions / sqlite — under the on-disk workspace."""
        prefix = str(self._config.system_files_path or "").strip()
        return self._workspace_path / prefix if prefix else self._workspace_path

    def _init_logging(self) -> None:
        """Install library-default logging if the process has no file handler yet."""
        from octop_harness.observability.logging import ensure_logging, logging_scope

        with logging_scope(self._agent_id):
            ensure_logging()

    def _init_mcp(self) -> None:
        """Validate MCP defaults and load tools from ``config.mcp_server_configs``."""
        cfg = self._config
        validate_mcp_default_servers(cfg.mcp_default_servers, cfg.mcp_server_configs)
        self._mcp_tools = []
        if not cfg.mcp_server_configs:
            self._mcp_tool_name_set = frozenset()
            return
        try:
            self._mcp_tools = load_mcp_tools(cfg.mcp_server_configs)
        except DEFENSIVE_OP_ERRORS:
            logger.warning(
                "Failed to load MCP tools from %s",
                sorted(cfg.mcp_server_configs),
                exc_info=True,
            )
        self._mcp_tool_name_set = mcp_tool_names(self._mcp_tools)

    def _init_model_factory(self, injected: ChatModelFactory | None) -> ChatModelFactory:
        """Resolve the model factory: injected → config providers → env detection."""
        cfg = self._config
        if injected is not None:
            # Orca (and similar hosts) keep providers on HarnessAgentManager.shared_factory
            # only; per-agent HarnessAgentConfig may omit providers. Mirror the shared
            # factory here so pick_default_model_ref / pick_multimodal_model_ref work.
            if not cfg.providers:
                cfg.providers = injected.provider_configs()
            return injected

        if cfg.providers:
            return ChatModelFactory(cfg.providers, agent_config=cfg)

        from octop_harness.config.env import detect_providers_from_env

        detected_providers, detected_default = detect_providers_from_env()
        if not detected_providers:
            raise ValueError(
                "HarnessAgent requires providers on the config, an injected "
                "model_factory (e.g. from HarnessAgentManager), or provider "
                "environment variables (OPENAI_API_KEY, HARNESS_PROVIDER_*_API_KEY, …).",
            )
        cfg.providers = detected_providers
        if detected_default is not None and cfg.default_model is None:
            cfg.default_model = detected_default
        if cfg.default_model is not None:
            cfg._check_model_ref("default_model", cfg.default_model)
        if cfg.multimodal_model is not None:
            cfg._check_model_ref("multimodal_model", cfg.multimodal_model)
        return ChatModelFactory(detected_providers, agent_config=cfg)

    def _bind_plugin_model_factory(self) -> None:
        from octop_harness.plugins.context import PluginContext
        from octop_harness.plugins.registry import PluginRegistry

        factory = self._model_factory
        get_protocol = self._get_protocol
        for loaded in PluginRegistry().all_loaded():
            ctx = loaded.context
            if isinstance(ctx, PluginContext):
                ctx.bind_model_factory(factory, get_protocol=get_protocol)

    def _init_graph(self) -> None:
        """Compile the deep-agent graph and snapshot the seed model ref."""
        # Promote empty-tuple (bootstrap suppression) to None once bootstrap completes,
        # so the unified loader includes the standard workspace context files.
        memory_override = None if self._config.memory == () and self.is_bootstrapped() else self._config.memory
        # Strong memory is user-owned context even when bootstrap or structured
        # memory is disabled. Keep declared paths stable, including absent files;
        # deepagents owns loading, session snapshots, formatting and caching.
        memory_files = DEFAULT_MEMORY_FILES if memory_override is None else memory_override
        memory_paths = self._workspace.memory_paths(
            tuple(dict.fromkeys([*memory_files, "MEMORY.md", "USER.md"])), include_missing=True
        )
        tools = self._build_tools()
        middleware = [
            DeepAgentsMemoryMiddleware(
                backend=self._backend,
                sources=memory_paths,
                # AGENTS.md owns memory policy. Suppress upstream's default
                # edit_file learning instructions, keeping only the wrapper.
                system_prompt="<agent_memory>\n{agent_memory}\n</agent_memory>",
                add_cache_control=True,
            ),
            *self._build_middleware(),
        ]
        if self._config.todos_enabled:
            from langchain.agents.middleware import TodoListMiddleware

            middleware = [TodoListMiddleware(), *middleware]
        self._base_graph = self._build_graph(
            tools=tools,
            middleware=middleware,
            skills=self._workspace.skill_paths(extra=self._config.skills_dir),
            memory=memory_paths,
        )
        # Bound at compile time; ModelRouterMiddleware swaps on every call.
        self._seed_model_ref = self._config.pick_default_model_ref()
        self._graph = self._wrap_graph(self._base_graph)
        self._sync_protocol_graph()

    def set_langfuse_callbacks(self, callbacks: list[Any] | None) -> None:
        """Bind Langfuse (or other) callbacks on the compiled graph via ``with_config``."""
        self._langfuse_callbacks = list(callbacks) if callbacks else None
        base = getattr(self, "_base_graph", None)
        if base is not None:
            self._graph = self._wrap_graph(base)
            self._sync_protocol_graph()

    def _wrap_graph(self, graph: Any) -> Any:
        if self._langfuse_callbacks:
            return graph.with_config({"callbacks": self._langfuse_callbacks})
        return graph

    def _sync_protocol_graph(self) -> None:
        """Point cached protocol wrappers at the current compiled graph.

        ``ChatProtocol`` instances capture ``graph`` at construction time.
        Callers (e.g. Orca gateway MCP injection) may recompile the graph after
        protocols were warmed in ``__init__``; without this refresh, streaming
        would keep using the pre-injection graph and miss in-process MCP tools.
        """
        for proto in self._protocols.values():
            proto._graph = self._graph

    def _init_protocols(self) -> None:
        """Warm the default protocol and prepare the per-name cache."""
        self._protocol = self._get_protocol(self._config.protocol)

    def _build_backend(self) -> BackendProtocol:
        """Resolve ``config.backend`` (string / dict / instance / None).

        For local-class backends with no explicit ``root_dir``, we pass
        ``workspace_dir`` so the backend's virtual ``/`` lines up with
        the workspace on disk.
        """
        from octop_harness.observability.logging import logging_scope

        with logging_scope(self._agent_id):
            spec = self._config.backend
            if isinstance(spec, dict) and spec.get("type") == "docker":
                spec = dict(spec)
                scope = str(spec.get("sandbox_scope") or "agent").strip().lower()
                # Inject agent_id for agent-scoped naming when the host did not set it.
                if (
                    scope == "agent"
                    and not spec.get("container_name")
                    and not spec.get("agent_id")
                    and not spec.get("sandbox_id")
                ):
                    key = self._agent_id or self._config.name
                    if key:
                        spec["agent_id"] = str(key)
                if self._config.system_files_path:
                    spec.setdefault("system_files_path", self._config.system_files_path)
            return resolve_backend(
                spec,
                workspace_dir=self._workspace_path,
                system_files_path=self._config.system_files_path,
                explicit_virtual_paths=self._config.explicit_virtual_paths,
            )

    def _wire_workspace_dotenv_for_execute(self) -> None:
        """Wire workspace ``.env`` reads for execute (same path as env_file tools)."""
        from octop_harness.backends.local_shell import HarnessLocalShellBackend
        from octop_harness.runtime_env import backend_workspace_dotenv_reader

        target = getattr(self._backend, "default", self._backend)
        if not isinstance(target, HarnessLocalShellBackend):
            return

        target.set_workspace_dotenv_reader(backend_workspace_dotenv_reader(self._workspace))

    def _close_backend(self) -> None:
        """Close the backend when it exposes a ``close`` hook (idempotent)."""
        close = getattr(self._backend, "close", None)
        if callable(close):
            with contextlib.suppress(Exception):
                close()

    def _build_tools(self) -> list[Any]:
        """Compose builtin + web-search + memory + user tools."""
        cfg = self._config
        tools: list[Any] = [
            CurrentTimeTool(cfg.default_timezone).as_tool(),
            web_fetch,
            browser_use,
            build_desktop_screenshot_tool(self._workspace),
            build_send_file_to_user_tool(self._workspace),
            *build_env_file_tools(self._workspace),
        ]
        tools.extend(load_web_search_tools(cfg.web_search_tools))
        if self._ask_user_active():
            tools.append(ask_user_question)
        if cfg.media_generation is not None and cfg.media_generation.has_api_key():
            tools.extend(build_media_generation_tools(self._workspace, cfg.media_generation))
        tools.extend(self._memory_runtime.build_tools())
        if cfg.explicit_virtual_paths:
            from octop_harness.backends.explicit_virtual_path import (
                build_virtual_to_native_tool,
            )

            tools.append(build_virtual_to_native_tool(self._backend))
        if cfg.tools:
            tools.extend(cfg.tools)
        if cfg.acp_delegate_enabled:
            tools.extend(self._build_acp_tools())
        if self._mcp_tools:
            tools.extend(self._mcp_tools)
        return tools

    def _ask_user_active(self) -> bool:
        """Whether ``ask_user_question`` should be mounted and interrupted on.

        Deliberately independent of ``SecurityPolicy``: the tool is a
        collaboration channel, not an approval gate, so it must work with the
        default policy (``hitl.enabled=False``).
        """
        cfg = self._config
        return bool(cfg.ask_user_enabled) and ASK_USER_TOOL_NAME not in cfg.tools_disabled

    def _resolve_interrupt_on(self) -> dict[str, Any]:
        """Merge security-derived HITL gates with the ask-user channel."""
        interrupt_on: dict[str, Any] = {}
        cfg = self._config
        if cfg.interrupt_on and self.is_bootstrapped():
            # Onboarding writes USER.md via file tools; HITL must not block bootstrap
            # (Dashboard chat, IM channels, and harness manager security reloads).
            interrupt_on.update(cfg.interrupt_on)
        if self._ask_user_active():
            # ``respond`` only: the human answers *instead of* running the tool.
            # The default description talks about "approval", which is wrong here.
            interrupt_on[ASK_USER_TOOL_NAME] = {
                "allowed_decisions": ["respond"],
                "description": "The agent is asking you to decide.",
            }
        return interrupt_on

    def _build_acp_tools(self) -> list[Any]:
        cfg = self._config
        from octop_harness.acp.models import ACPConfig
        from octop_harness.builtin.tools.acp_runner import build_acp_runner_tool

        acp_config = ACPConfig(runners=dict(cfg.acp_runners))
        if not acp_config.enabled_runner_names():
            return []
        try:
            return [
                build_acp_runner_tool(
                    service_key=str(self._workspace_path),
                    config=acp_config,
                    workspace_dir=self._workspace_path,
                ),
            ]
        except ImportError:
            logger.warning(
                "ACP delegate tool requested but agent-client-protocol is not installed; "
                "install octop-harness with the [acp] extra",
            )
            return []

    def _build_middleware(self) -> list[Any]:
        """Assemble the middleware chain in declared execution order.

        Order: bootstrap (front-loaded) → router → model_settings → session_header →
        skill_filter → tool_guard → filesystem_guard (outside-root soft-fail; deny
        rules when permissions + execution backend) → mcp_tools → retry →
        pii → media_offload → checkpoint_ts → memory → user middleware → team →
        conversation_mode → tools_filter → decision (only when enabled) → tool search →
        task tool ordering → context_usage.

        ``MediaOffloadMiddleware`` runs **after** PII (so PII still sees plain
        text) and **before** ``MemoryMiddleware`` so session logs store the
        lightweight placeholder rather than raw base64.

        ``CheckpointTsMiddleware`` stamps ``checkpoint_ts`` on newly appended
        messages so history loads do not need a full checkpoint scan.
        """
        cfg = self._config
        chain: list[Any] = [
            ModelRouterMiddleware(cfg, self._model_factory, get_protocol=self._get_protocol),
            ModelSettingsMiddleware(),
            SessionHeaderMiddleware(),
            SkillFilterMiddleware(config=cfg),
        ]

        if cfg.tool_guard_enabled:
            from octop_harness.middleware.tool_guard import ToolGuardMiddleware

            chain.append(
                ToolGuardMiddleware(
                    enabled=True,
                    mode=cfg.tool_guard_mode,
                    rules_dir=cfg.tool_guard_rules_dir,
                )
            )

        # Filesystem tool boundary: always soften outside-root ValueError; apply
        # deny rules only when permissions are set on an execution backend.
        from octop_harness.middleware.filesystem_guard import FilesystemGuardMiddleware

        fs_permissions = list(cfg.permissions) if cfg.permissions and spec_supports_execution(cfg.backend) else []
        root_dir, _virtual = self._peek_backend_mount()
        chain.append(
            FilesystemGuardMiddleware(
                fs_permissions,
                root_dir=root_dir,
                workspace_dir=cfg.workspace_dir,
                workspace=self._workspace,
            )
        )

        if cfg.mcp_server_configs:
            chain.append(
                MCPToolMiddleware(
                    server_names=frozenset(cfg.mcp_server_configs),
                    mcp_tool_names=self._mcp_tool_name_set,
                    default_servers=cfg.mcp_default_servers,
                )
            )

        if cfg.model_retry_enabled:
            chain.append(
                ModelRetryMiddleware(
                    max_retries=cfg.model_retry_max_retries,
                    initial_delay=cfg.model_retry_initial_delay,
                    max_delay=cfg.model_retry_max_delay,
                    on_failure="error",
                )
            )

        if cfg.pii_enabled:
            surfaces = set(cfg.pii_surfaces)
            chain.append(
                PIIMiddleware(
                    pii_type="api_key",
                    strategy=cfg.pii_strategy,
                    detector=detect_pii,
                    apply_to_input="input" in surfaces,
                    apply_to_output="output" in surfaces,
                    apply_to_tool_results="tool_results" in surfaces,
                )
            )

        if cfg.media_offload_enabled:
            chain.append(
                MediaOffloadMiddleware(
                    workspace=self._workspace,
                    min_bytes=cfg.media_offload_min_bytes,
                    media_offload_dir=cfg.media_offload_dir,
                )
            )

        chain.append(CheckpointTsMiddleware())

        memory_mw = self._memory_runtime.build_middleware()
        if memory_mw is not None:
            chain.append(memory_mw)

        if cfg.middleware:
            chain.extend(cfg.middleware)

        # After other prompt injectors so the optional ``@`` roster is a suffix
        # (stable prefix stays cacheable). Before tools_filter so peer tools
        # can still be hidden via ``tools_disabled``.
        if cfg.team_enabled and self._team_manager is not None:
            from octop_harness.middleware.peer import PeerAgentMiddleware

            chain.append(
                PeerAgentMiddleware(
                    self._team_manager,
                    language=cfg.language,
                    peer_invoke_mode=cfg.peer_invoke_mode,
                )
            )

        # After MCP / user middleware may add or filter tools, and before tool
        # search so ``tools_disabled`` names cannot leak into the search catalog.
        from octop_harness.middleware.conversation_mode import ConversationModeMiddleware

        chain.append(ConversationModeMiddleware())
        chain.append(ToolsFilterMiddleware(config=cfg))

        from octop_harness.decision import decision_active

        decision = cfg.decision
        if decision is not None and decision_active(decision):
            from octop_harness.middleware.decision import DecisionMiddleware

            chain.append(
                DecisionMiddleware(
                    config=decision,
                    team=self._team_manager,
                    language=cfg.language,
                )
            )

        # Search only the final model-visible tool set. In particular, this
        # must run after MCP and user filtering so hidden tools cannot leak
        # into either the client or provider search inventory.
        tool_search = self._build_tool_search_middleware()
        if tool_search is not None:
            chain.append(tool_search)

        # Run after all harness/user middleware that may add or filter tools so
        # the model sees ``task`` after the final shared tool set.
        if cfg.task_tool_last:
            chain.append(TaskToolLastMiddleware())

        # After tool-order normalization so the snapshot matches the final request.
        self._context_usage_mw = ContextUsageMiddleware(
            mcp_tool_names=self._mcp_tool_name_set,
            max_tokens=self._default_max_input_tokens(),
        )
        chain.append(self._context_usage_mw)

        bootstrap = self._build_bootstrap_middleware()
        if bootstrap is not None:
            chain.insert(0, bootstrap)

        return chain

    def _build_tool_search_middleware(self) -> Any | None:
        cfg = self._config
        deferred_tools = cfg.deferred_tools
        if cfg.media_generation is not None and cfg.media_generation.has_api_key() and cfg.media_generation.defer_tools:
            media_tools: set[str] = set()
            if cfg.media_generation.has_image_provider():
                media_tools.add("generate_image")
            if cfg.media_generation.has_video_provider():
                media_tools.add("generate_video")
            deferred_tools = deferred_tools | media_tools
        if not (deferred_tools or cfg.defer_mcp_tools) or cfg.tool_search_mode == "eager":
            return None
        return ToolSearchMiddleware(
            deferred_tools=deferred_tools,
            mcp_tool_names=self._mcp_tool_name_set,
            defer_mcp_tools=cfg.defer_mcp_tools,
            mode=cfg.tool_search_mode,
            fallback=cfg.tool_search_fallback,
        )

    def _build_bootstrap_middleware(self) -> BootstrapMiddleware | None:
        """Return bootstrap middleware when enabled and onboarding is pending."""
        if not self._config.bootstrap_enabled:
            return None
        mw = BootstrapMiddleware(
            self._workspace,
            bootstrap_file=self._config.bootstrap_file,
            bootstrap_marker=self._config.bootstrap_marker,
            on_complete=self._on_bootstrap_complete,
        )
        if mw.is_bootstrapped:
            return None
        return mw

    def _on_bootstrap_complete(self) -> None:
        """Called by BootstrapMiddleware once the marker file is written.

        Triggers a full config reload via ``on_bootstrap_complete`` when the
        caller (e.g. Orca) has registered one — this lets the caller rebuild
        the agent with the correct ``system_prompt`` and ``memory`` from the
        database.  Falls back to a local ``_init_graph`` recompile so that
        memory files written during bootstrap (USER.md, SOUL.md) are loaded
        even when no external reload hook is registered.
        """
        logger.info("Bootstrap complete — triggering graph reload (hook=%s)", self.on_bootstrap_complete is not None)
        if self.on_bootstrap_complete is not None:
            try:
                self.on_bootstrap_complete()
            except DEFENSIVE_OP_ERRORS:
                logger.exception("on_bootstrap_complete hook raised an exception")
        else:
            self._init_graph()

    def _resolve_subagents(self, *, parent_tools: list[Any] | None = None) -> list[Any]:
        """Merge workspace markdown subagents with config overrides."""
        from octop_harness.mcp import filter_tools_for_mcp_servers
        from octop_harness.subagents.loader import load_subagents_from_workspace, merge_subagents

        cfg = self._config
        config_specs = list(cfg.subagents or [])
        if not cfg.subagents_auto_load:
            return [dict(spec) for spec in config_specs]
        loaded = load_subagents_from_workspace(
            self._workspace,
            subagents_path=cfg.subagents_path,
            parent_tools=parent_tools,
        )
        specs = merge_subagents(loaded, config_specs)
        # Subagents do not inherit the parent's middleware chain, so the
        # MCPToolMiddleware that hides MCP tools on the main agent never runs for
        # them. Strip every MCP tool here at compile time so subagents match the
        # main agent's default (MCP hidden) tool surface.
        mcp_names = self._mcp_tool_name_set
        server_names = frozenset(cfg.mcp_server_configs)
        for spec in specs:
            # A subagent that omits ``tools:`` inherits the parent tool set; we
            # still resolve and reassign it so the gated set is pinned on the
            # spec instead of leaking the full compiled graph.
            raw = spec.get("tools")
            if raw is None:
                if parent_tools is None:
                    continue
                base: list[Any] = list(parent_tools)
            else:
                base = list(raw)
            spec["tools"] = filter_tools_for_mcp_servers(
                base,
                mcp_tool_names=mcp_names,
                server_names=server_names,
                active_servers=None,
            )
            # Subagents run as nested graphs without the parent's HITL config,
            # so an ``ask_user_question`` call there can never reach a human.
            # Hide it instead of letting them burn a turn on the fallback.
            spec["tools"] = [t for t in spec["tools"] if _tool_name_of(t) != ASK_USER_TOOL_NAME]
        return specs

    def _build_graph(
        self,
        *,
        tools: list[Any],
        middleware: list[Any],
        skills: list[str],
        memory: list[str],
    ) -> Any:
        cfg = self._config
        checkpointer = self._resolve_checkpointer()
        self._checkpointer_instance: Any = checkpointer

        kwargs: dict[str, Any] = {
            "model": self._build_seed_model(),
            "tools": tools,
            "middleware": middleware,
            "backend": self._backend,
            "name": cfg.name,
            "debug": cfg.debug,
        }
        base_prompt = cfg.system_prompt.rstrip() if cfg.system_prompt else ""
        work_dir = self._agent_visible_workspace_dir()
        # Soft policy for the model only — no tool rewrite / resolve remapping.
        work_dir_text = work_dir.as_posix()
        directive = (
            f"Your working directory is {work_dir_text}. "
            "Keep routine filesystem tool paths (ls, read_file, write_file, "
            "edit_file, glob, grep) inside this workspace — prefer relative paths "
            f"such as `.` or `SOUL.md`, or paths under {work_dir_text} "
            f"(e.g. `{work_dir_text.rstrip('/')}/notes.txt`). "
            "Do not treat `/` as the workspace: `/` is the backend root "
            "(often the user home directory on Windows). "
            "Do not invent host home prefixes like `/home/...` or `/Users/...`. "
            "Leave the workspace only when the user explicitly asks. "
            "For new AI-generated artifacts, prefer a subdirectory such as "
            "`generated/` over the workspace root."
        )
        if cfg.media_generation is None:
            directive += (
                " Image and video generation tools are not configured in this runtime. "
                "If the user asks for generated media, state that configuration is required; "
                "do not claim that media was generated."
            )
        elif not cfg.media_generation.has_api_key():
            directive += (
                " Image and video generation tools are unavailable because media-provider "
                "credentials are missing. If the user asks for generated media, ask them to "
                "configure credentials in the host application; do not retry or claim success."
            )
        from octop_harness.backends.explicit_virtual_path import EXPLICIT_VIRTUAL_PATH_PROMPT

        directive += f" {EXPLICIT_VIRTUAL_PATH_PROMPT}" if cfg.explicit_virtual_paths else ""
        kwargs["system_prompt"] = (
            base_prompt + "\n\n" + directive + "\n\n" + render_slash_skill_prompt(language=cfg.language)
        ).strip()
        resolved_subagents = self._resolve_subagents(parent_tools=tools)
        if resolved_subagents:
            kwargs["subagents"] = resolved_subagents
        if skills:
            kwargs["skills"] = skills
        if memory:
            kwargs["memory"] = memory
        if cfg.permissions and not spec_supports_execution(cfg.backend):
            kwargs["permissions"] = cfg.permissions
        interrupt_on = self._resolve_interrupt_on()
        if interrupt_on:
            kwargs["interrupt_on"] = interrupt_on
        if cfg.response_format is not None:
            kwargs["response_format"] = cfg.response_format
        if checkpointer is not None:
            kwargs["checkpointer"] = checkpointer

        # Indirect through the module so test patches on
        # ``deepagents.create_deep_agent`` are picked up at call time.
        # Capture the main-agent SummarizationMiddleware (last factory call)
        # so ``/compact`` can retune keep on that instance (same backend /
        # session id / apply-event) instead of building a second MW.
        import deepagents.graph as deepagents_graph

        orig_factory = getattr(deepagents_graph, "create_summarization_middleware", None)
        if not callable(orig_factory):
            return deepagents.create_deep_agent(**kwargs)

        captured: list[Any] = []

        def _capture_summarization_middleware(*args: Any, **kwargs: Any) -> Any:
            from octop_harness.middleware.memory_recall import count_tokens_with_recall

            # Summarization wraps the memory middleware and sees clean state
            # messages. Include their recall snapshots in its budget/keep math.
            kwargs.setdefault("token_counter", count_tokens_with_recall)
            mw = orig_factory(*args, **kwargs)
            captured.append(mw)
            return mw

        deepagents_graph.create_summarization_middleware = (  # type: ignore[attr-defined]
            _capture_summarization_middleware
        )
        try:
            graph = deepagents.create_deep_agent(**kwargs)
        finally:
            deepagents_graph.create_summarization_middleware = orig_factory  # type: ignore[attr-defined]
        if captured:
            self._summarization_mw = captured[-1]
        return graph

    def _build_seed_model(self) -> Any:
        """Build the *initial* model bound at graph compile time.

        Installs a turn-aware ``profile`` so deepagents
        ``SummarizationMiddleware`` fraction thresholds follow the same turn
        model-ref rules as ``ModelRouterMiddleware`` (explicit override /
        default). Invoke/summary LLM still use the seed; the router swaps the
        chat model separately.
        """
        from octop_harness.middleware.turn_aware_profile import install_turn_aware_profile

        seed = self._model_factory.get_chat_model(self._config.pick_default_model_ref())
        return install_turn_aware_profile(
            seed,
            factory=self._model_factory,
            pick_default_ref=self._config.pick_default_model_ref,
            pick_multimodal_ref=self._config.pick_multimodal_model_ref,
        )

    def _resolve_checkpointer(self) -> Any:
        """Resolve the checkpointer to use.

        Resolution order:

        1. ``config.checkpointer is False`` → opt out (return ``False``).
        2. ``config.checkpointer`` is an instance → use it as-is.
        3. The memory integration is built (memory_enabled=True) → reuse its
           backing ``Memory`` instance.
           ``Memory`` inherits ``BaseCheckpointSaver`` and shares its
           database with the rest of the memory system, so we get a
           single source of truth for both checkpoints and recall.
        4. Default fallback → AsyncSqliteSaver under ``{workspace}/checkpoints.sqlite``.

        Returns ``None`` only when all of the above fail (e.g. langgraph
        sqlite saver missing) — deep-agent then falls back to its own
        in-memory default.
        """
        explicit = self._config.checkpointer
        if explicit is False:
            return False
        if explicit is not None:
            return explicit

        # Reuse the Memory instance as checkpointer when available — it is
        # already a ``BaseCheckpointSaver`` subclass backed by the same DB.
        memory = self._memory_runtime.memory
        if memory is not None:
            return memory

        if _AsyncSqliteSaver is None or aiosqlite is None:  # pragma: no cover - dependency listed
            logger.warning("langgraph-checkpoint-sqlite is unavailable; running without checkpointer")
            return None

        sqlite_path = self._host_system_dir() / "checkpoints.sqlite"
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = aiosqlite.connect(str(sqlite_path))
            # ``aiosqlite.Connection`` drives a worker thread (started lazily on
            # first await). Mark it daemon so a forgotten ``close()`` doesn't
            # block interpreter shutdown; checkpoint writes are committed per
            # step, so the on-disk DB stays consistent. The thread lives on the
            # private ``_thread`` attr in current aiosqlite; older releases make
            # ``Connection`` itself a ``Thread``.
            worker: Any = getattr(conn, "_thread", conn)
            with contextlib.suppress(AttributeError, RuntimeError, TypeError):
                worker.daemon = True
            saver = _build_async_sqlite_saver(conn)
        except DEFENSIVE_OP_ERRORS:
            logger.warning(
                "Could not open AsyncSqliteSaver at %s; running without checkpointer",
                sqlite_path,
                exc_info=True,
            )
            return None

        # The connection lazily connects on first async use; we keep it for
        # the agent's lifetime and close it in ``close()``.
        self._checkpointer_conn: Any = conn
        return saver

    def _release_checkpointer(self) -> None:
        """Close the async SQLite connection opened by :meth:`_resolve_checkpointer`."""
        conn: Any = getattr(self, "_checkpointer_conn", None)
        if conn is None:
            return
        _sync_close_sqlite_connection(conn)
        self._checkpointer_conn = None

    async def _release_checkpointer_async(self) -> None:
        """Await ``aiosqlite`` shutdown when closing from an async context."""
        conn: Any = getattr(self, "_checkpointer_conn", None)
        if conn is None:
            return
        await _async_close_sqlite_connection(conn)
        self._checkpointer_conn = None

    # ------------------------------------------------------------------
    # Internal: invocation
    # ------------------------------------------------------------------

    def _prepare_call(
        self,
        request: ChatRequest | str | dict[str, Any],
        protocol: str | None,
    ) -> tuple[Any, Any, ChatProtocol]:
        """Normalize a request into ``(messages, config, protocol)``.

        Shared by ``call`` / ``stream`` / ``stream_events``.
        """
        req = ChatRequest.coerce(request)
        return req.normalize_messages(), req.to_runnable_config(), self._get_protocol(protocol)

    def _get_protocol(self, name: str | None) -> ChatProtocol:
        """Resolve a protocol by name (cached). ``None`` → config default."""
        key = name or self._config.protocol
        proto = self._protocols.get(key)
        if proto is None:
            proto = resolve_protocol(key, self._graph)
            self._protocols[key] = proto
        return proto


async def _async_close_sqlite_connection(conn: Any) -> None:
    """Close an ``aiosqlite.Connection`` via its async API, with sync fallback."""
    try:
        await conn.close()
    except DEFENSIVE_OP_ERRORS:  # pragma: no cover - defensive shutdown
        _sync_close_sqlite_connection(conn)


def _sync_close_sqlite_connection(conn: Any) -> None:
    """Close an ``aiosqlite.Connection`` synchronously for agent teardown.

    ``aiosqlite.Connection.close()`` is async. During pytest teardown (or any
    sync ``close()`` while an event loop is running) scheduling ``ensure_future``
    leaves the underlying ``sqlite3.Connection`` open until GC — which trips
    ``ResourceWarning`` under pytest's strict unraisable hook. Closing the
    private ``_connection`` first is safe: checkpoint writes are committed per
    step, and ``close()`` is idempotent.
    """
    raw = getattr(conn, "_connection", None)
    if raw is not None:
        with contextlib.suppress(Exception):
            raw.close()
    stop_fn = getattr(conn, "stop", None)
    if callable(stop_fn):
        with contextlib.suppress(Exception):
            fut = stop_fn()
            if fut is not None:
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    with contextlib.suppress(Exception):
                        asyncio.run(fut)
    if raw is None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            with contextlib.suppress(Exception):
                asyncio.run(conn.close())


def _build_async_sqlite_saver(conn: Any) -> Any:
    """Construct an ``AsyncSqliteSaver``, tolerating a sync construction context.

    ``AsyncSqliteSaver.__init__`` calls ``asyncio.get_running_loop()``. That
    works when the agent is built inside an event loop (the common case, since
    ``HarnessAgentManager.create`` is typically called from ``async`` code), but
    raises when built synchronously. In that case we spin a throwaway loop just
    for construction — only the async saver methods are ever used, and they bind
    to the *running* loop at call time, so the captured loop is irrelevant.
    """
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_new_async_saver(conn))
        finally:
            loop.close()
    return _AsyncSqliteSaver(conn)


async def _new_async_saver(conn: Any) -> Any:
    return _AsyncSqliteSaver(conn)


__all__ = ["HarnessAgent", "InitResult"]
