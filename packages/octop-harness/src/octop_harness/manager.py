"""Multi-agent registry orchestration: stream/call + team subsystem."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import aclosing, asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from octop_harness.agent import HarnessAgent
from octop_harness.config import HarnessAgentConfig, ProviderConfig
from octop_harness.mcp import merge_mcp_server_configs
from octop_harness.memory.store import hold_shared_memory
from octop_harness.observability.langfuse import LangfuseConfig, LangfuseTracer
from octop_harness.observability.logging import (
    DEFAULT_LOG_BACKUP_COUNT,
    DEFAULT_LOG_MAX_BYTES,
    LogLevel,
    resolve_log_dir,
    setup_logging,
    use_host_logging,
)
from octop_harness.providers import ProviderPreset, load_provider_templates
from octop_harness.registry import AgentEntry, AgentRegistry, generate_agent_id
from octop_harness.request import ChatRequest
from octop_harness.security.models import SecurityPolicy
from octop_harness.teams.team_manager import TeamManager

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

    from octop_harness.context_usage import ContextUsage
    from octop_harness.llm.factory import ChatModelFactory
    from octop_harness.teams.processor import TeamProcessor

# Re-export for backward compatibility.
__all__ = ["AgentEntry", "HarnessAgentManager"]

logger = logging.getLogger(__name__)


class HarnessAgentManager:
    """In-memory registry for managing multiple HarnessAgent instances.

    Runtime diagnostic logging is configured once on this manager
    (``log_dir`` / ``log_level`` / rotation), not on each agent config.
    One process should use one ``log_dir``: a later manager (or
    ``setup_logging`` call) with a different path replaces the package
    file handler. Pass ``file_logging=False`` when the host process already
    writes a log file; records then propagate instead of opening
    ``YYYY-MM-DD.log``.
    """

    def __init__(
        self,
        providers: list[ProviderConfig] | None = None,
        mcp_server_configs: dict[str, Any] | None = None,
        langfuse: LangfuseConfig | None = None,
        team_processor: TeamProcessor | None = None,
        *,
        log_dir: str | Path | None = None,
        log_level: LogLevel | None = None,
        log_max_bytes: int = DEFAULT_LOG_MAX_BYTES,
        log_backup_count: int = DEFAULT_LOG_BACKUP_COUNT,
        file_logging: bool = True,
    ) -> None:
        from octop_harness.llm.factory import ChatModelFactory

        self._shared_factory: ChatModelFactory | None = ChatModelFactory(providers) if providers else None
        self._shared_mcp_configs: dict[str, Any] = dict(mcp_server_configs or {})
        self._registry = AgentRegistry()
        self._cancel_events: dict[tuple[str, str], asyncio.Event] = {}
        self._langfuse: LangfuseTracer | None = LangfuseTracer(langfuse) if langfuse and langfuse.configured else None
        self._security_policy: SecurityPolicy = SecurityPolicy.defaults()
        self._log_dir: Path | None
        self._log_file: Path | None
        if file_logging:
            self._log_dir = resolve_log_dir(log_dir)
            self._log_file = setup_logging(
                self._log_dir,
                level=log_level,
                max_bytes=log_max_bytes,
                backup_count=log_backup_count,
            )
        else:
            use_host_logging()
            self._log_dir = None
            self._log_file = None
        self._team = TeamManager(self._registry)
        self._team.bind_invocation_hooks(
            enrich_request=self._enrich_request,
            after_call=self._flush_langfuse,
        )
        if team_processor is not None:
            self._team.set_processor(team_processor)

    @property
    def team(self) -> TeamManager:
        """Team/inbox subsystem (peer discovery, sync/async collaboration)."""
        return self._team

    @property
    def shared_factory(self) -> ChatModelFactory | None:
        return self._shared_factory

    @property
    def shared_mcp_configs(self) -> dict[str, Any]:
        return dict(self._shared_mcp_configs)

    def set_security_policy(self, policy: SecurityPolicy | None) -> None:
        self._security_policy = policy or SecurityPolicy.defaults()
        self._rebuild_all_agents()

    def rebuild_all_agents(self) -> None:
        """Rebuild every running agent in-place (e.g. after security policy changes on disk)."""
        self._rebuild_all_agents()

    def _rebuild_all_agents(self) -> None:
        for agent_id in self._registry.agent_ids():
            self._rebuild_agent(agent_id)

    def _rebuild_agent(self, agent_id: str) -> None:
        try:
            entry = self._registry.get(agent_id)
        except KeyError:
            return
        metadata = dict(entry.metadata)
        tags = list(entry.tags)
        config = self._apply_security_policy(entry.config)
        # Pin Memory so remove-then-create keeps the same backend / checkpointer
        # pool. MCP / policy changes only compile a new graph.
        with hold_shared_memory(entry.config, getattr(entry.agent, "_workspace_path", None)):
            self.remove_agent(agent_id)
            self._register_agent(
                config,
                metadata=metadata,
                tags=tags,
                agent_id=agent_id,
                init_workspace=False,
            )

    def _register_agent(
        self,
        config: HarnessAgentConfig | Any,
        *,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        agent_id: str,
        init_workspace: bool = True,
    ) -> AgentEntry:
        effective_config = replace(
            config,
            mcp_server_configs=merge_mcp_server_configs(self._shared_mcp_configs, config.mcp_server_configs),
        )
        effective_config = self._apply_security_policy(effective_config)
        agent = HarnessAgent(
            effective_config,
            model_factory=self._shared_factory,
            team_manager=self._team if effective_config.team_enabled else None,
            agent_id=agent_id,
        )
        if init_workspace:
            seeded = agent.init_workspace()
            # Templates, skills and subagent manifests are read while compiling
            # the graph, so only a seed that actually wrote something
            # invalidates the graph built in ``HarnessAgent.__init__``.
            if (
                seeded.templates_created
                or seeded.templates_overwritten
                or seeded.skills_synced
                or seeded.agents_created
                or seeded.agents_overwritten
            ):
                agent._init_graph()
        if self._langfuse is not None:
            agent.set_langfuse_callbacks(self._langfuse.callbacks)
        entry = AgentEntry(
            agent_id=agent_id,
            agent=agent,
            config=effective_config,
            metadata=dict(metadata or {}),
            tags=list(tags or []),
            created_at=datetime.now(tz=UTC),
        )
        self._registry.add(entry)
        return entry

    def _apply_security_policy(self, config: Any) -> Any:
        return self._security_policy.apply_to_config(config)

    def set_langfuse(self, config: LangfuseConfig | None) -> None:
        if config and config.configured:
            if self._langfuse is None:
                self._langfuse = LangfuseTracer(config)
            else:
                self._langfuse.set_config(config)
        elif self._langfuse is not None:
            self._langfuse.set_config(None)
            self._langfuse = None
        self._sync_langfuse_to_agents()

    def _sync_langfuse_to_agents(self) -> None:
        callbacks = self._langfuse.callbacks if self._langfuse else None
        for entry in self._registry.values():
            entry.agent.set_langfuse_callbacks(callbacks)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close all agents and release resources (idempotent, sync)."""
        self._team.close()
        for entry in self._registry.values():
            entry.agent.close()
        self._registry.clear()
        if self._shared_factory is not None:
            self._shared_factory.close()

    async def aclose(self) -> None:
        """Async shutdown: drain the team inbox before closing agents."""
        await self._team.aclose()
        for entry in self._registry.values():
            await entry.agent.aclose()
        self._registry.clear()
        if self._shared_factory is not None:
            await self._shared_factory.aclose()

    def __enter__(self) -> HarnessAgentManager:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    async def __aenter__(self) -> HarnessAgentManager:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # CRUD (delegates to registry)
    # ------------------------------------------------------------------

    def create_agent(
        self,
        config: Any,
        *,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        agent_id: str | None = None,
        init_workspace: bool = True,
    ) -> AgentEntry:
        aid = agent_id or generate_agent_id(occupied=set(self._registry.agent_ids()))
        return self._register_agent(
            config,
            metadata=metadata,
            tags=tags,
            agent_id=aid,
            init_workspace=init_workspace,
        )

    def get_agent(self, agent_id: str) -> AgentEntry:
        return self._registry.get(agent_id)

    def remove_agent(self, agent_id: str) -> None:
        entry = self._registry.remove(agent_id)
        entry.agent.close()

    async def acreate_agent(
        self,
        config: Any,
        *,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        agent_id: str | None = None,
        init_workspace: bool = True,
    ) -> AgentEntry:
        """Off-loop wrapper around :meth:`create_agent` (graph compile blocks the event loop)."""
        return await asyncio.to_thread(
            self.create_agent,
            config,
            metadata=metadata,
            tags=tags,
            agent_id=agent_id,
            init_workspace=init_workspace,
        )

    async def aremove_agent(self, agent_id: str) -> None:
        """Drop one agent and await resource release on this event loop.

        Sync :meth:`close` must not run in ``to_thread``: aiosqlite is bound
        to this loop, and the worker-thread fallback (``asyncio.run`` on
        ``stop()`` / ``close()``) waits for a loop that is itself waiting
        for the worker — the hang seen when Octop reloads MCP mid-chat.
        """
        try:
            entry = self._registry.remove(agent_id)
        except KeyError:
            return
        await entry.agent.aclose()

    async def arebuild_agent(
        self,
        agent_id: str,
        config: Any,
        *,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> AgentEntry:
        """Replace one agent with a fresh runtime compiled from *config*."""
        try:
            entry = self.get_agent(agent_id)
        except KeyError:
            return await self.acreate_agent(
                config,
                agent_id=agent_id,
                metadata=metadata,
                tags=tags,
                init_workspace=False,
            )
        resolved_metadata = dict(metadata if metadata is not None else entry.metadata)
        resolved_tags = list(tags if tags is not None else entry.tags)
        with hold_shared_memory(entry.config, getattr(entry.agent, "_workspace_path", None)):
            await self.aremove_agent(agent_id)
            return await self.acreate_agent(
                config,
                agent_id=agent_id,
                metadata=resolved_metadata,
                tags=resolved_tags,
                init_workspace=False,
            )

    def list_agents(
        self,
        *,
        agent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> list[AgentEntry]:
        return self._registry.list(agent_id=agent_id, metadata=metadata, tags=tags)

    # ------------------------------------------------------------------
    # Invocation helpers
    # ------------------------------------------------------------------

    async def _enrich_request(self, agent_id: str, request: ChatRequest) -> ChatRequest:
        if not request.agent_id:
            request.agent_id = agent_id
        if self._langfuse is not None:
            return self._langfuse.enrich_request(request)
        return request

    async def _prepare_request(
        self,
        agent_id: str,
        request: ChatRequest | str | dict[str, Any],
    ) -> ChatRequest:
        req = ChatRequest.coerce(request)
        req = await self._enrich_request(agent_id, req)
        if not req.agent_id:
            req = replace(req, agent_id=agent_id)
        return req

    async def _flush_langfuse(self) -> None:
        if self._langfuse is not None:
            await self._langfuse.flush_async()

    @asynccontextmanager
    async def _cancellable_stream(self, agent_id: str, thread_id: str) -> AsyncGenerator[asyncio.Event, None]:
        key = (agent_id, thread_id)
        event = asyncio.Event()
        self._cancel_events[key] = event
        try:
            yield event
        finally:
            self._cancel_events.pop(key, None)
            await self._flush_langfuse()

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    async def stream(
        self,
        agent_id: str,
        request: ChatRequest,
        **kwargs: Any,
    ) -> AsyncGenerator[Any, None]:
        entry = self._registry[agent_id]
        prepared = await self._prepare_request(agent_id, request)
        async with aclosing(entry.agent.stream(prepared, **kwargs)) as chunks:
            async for chunk in chunks:
                yield chunk

    async def call(
        self,
        agent_id: str,
        request: ChatRequest,
        **kwargs: Any,
    ) -> dict[str, Any]:
        entry = self._registry[agent_id]
        prepared = await self._prepare_request(agent_id, request)
        try:
            return await entry.agent.call(prepared, **kwargs)
        finally:
            await self._flush_langfuse()

    async def get_history(
        self,
        agent_id: str,
        thread_id: str,
        *,
        limit: int = 50,
        before: str | None = None,
    ) -> list[BaseMessage]:
        entry = self._registry[agent_id]
        return await entry.agent.aget_history(thread_id, limit=limit, before=before)

    async def get_context_usage(
        self,
        agent_id: str,
        thread_id: str,
        *,
        max_tokens: int | None = None,
    ) -> ContextUsage:
        entry = self._registry[agent_id]
        return await entry.agent.aget_context_usage(thread_id, max_tokens=max_tokens)

    def cancel(self, agent_id: str, thread_id: str) -> None:
        if event := self._cancel_events.get((agent_id, thread_id)):
            event.set()
        if agent_id in self._registry:
            self._registry[agent_id].agent.cancel(thread_id)

    def get_thread_model(self, agent_id: str, thread_id: str) -> str | None:
        if agent_id not in self._registry:
            return None
        return self._registry[agent_id].agent.get_thread_model(thread_id)

    def set_thread_model(self, agent_id: str, thread_id: str, model: str) -> None:
        if agent_id not in self._registry:
            return
        self._registry[agent_id].agent.set_thread_model(thread_id, model)

    def clear_thread_model(self, agent_id: str, thread_id: str) -> None:
        if agent_id not in self._registry:
            return
        self._registry[agent_id].agent.clear_thread_model(thread_id)

    async def resume_hitl(
        self,
        agent_id: str,
        thread_id: str,
        decisions: list[dict[str, Any]],
        **kwargs: Any,
    ) -> AsyncGenerator[Any, None]:
        entry = self._registry[agent_id]
        async with (
            self._cancellable_stream(agent_id, thread_id) as event,
            aclosing(entry.agent.resume_hitl(thread_id, decisions, **kwargs)) as chunks,
        ):
            async for chunk in chunks:
                if event.is_set():
                    break
                yield chunk

    # ------------------------------------------------------------------
    # Providers
    # ------------------------------------------------------------------

    def add_provider(self, provider: ProviderConfig) -> None:
        if self._shared_factory is None:
            from octop_harness.llm.factory import ChatModelFactory

            self._shared_factory = ChatModelFactory([provider])
            return
        factory = self._shared_factory
        factory._providers[provider.id] = provider
        factory.clear_provider_cache(provider.id)

    def remove_provider(self, provider_id: str) -> None:
        if self._shared_factory is None:
            return
        factory = self._shared_factory
        factory._providers.pop(provider_id, None)
        factory.clear_provider_cache(provider_id)

    def list_provider_templates(
        self,
        templates_path: str | Path | None = None,
    ) -> list[ProviderPreset]:
        return load_provider_templates(templates_path)
