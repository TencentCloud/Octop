"""AgentManager — process-wide singleton managing all HarnessAgent instances."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field, fields, replace
from typing import TYPE_CHECKING, Any, cast

from harness_agent import HarnessAgent, HarnessAgentConfig, HarnessAgentManager
from harness_agent.security.models import SecurityPolicy

from octop.i18n.domains.agents import NO_MODELS_CONFIGURED, format_agent_start_error
from octop.infra.agents.acp_settings import ACPSettingsStore
from octop.infra.agents.langfuse import LangfuseSettings, LangfuseSettingsStore
from octop.infra.agents.providers import ProviderStore, sync_providers_to_harness
from octop.infra.agents.security import SecuritySettingsStore, ToolGuardRulesStore
from octop.infra.backend.resolver import (
    backend_spec_supports_execution,
    default_agent_backend_spec,
    resolve_agent_backend_spec,
)
from octop.infra.connectors.builder import (
    build_mcp_server_configs_for_user,
    inject_missing_gateway_tools,
)
from octop.infra.connectors.service import ConnectorService
from octop.infra.db.repos.audit import ACTOR_SYSTEM
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.ulid import new_short_id

if TYPE_CHECKING:
    from octop.config import OctopConfig
    from octop.infra.agents.experts.catalog import ExpertCatalog
    from octop.infra.agents.plugins.manager import PluginManager
    from octop.infra.cron.manager import CronManager
    from octop.infra.db.repos.agents import AgentRow
    from octop.infra.db.services import RepoBundle
    from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)

# Bounded parallelism for awaited provider/active-model reload batches.
_PROVIDER_RELOAD_CONCURRENCY = 6

# harness-memory builds SQLite table names as ``{namespace}_*``. The namespace
# must be a valid bare SQL identifier: start with a letter, only [A-Za-z0-9_].
_MEMORY_NS_PREFIX = "agent_"

_AGENT_STATES_NEEDING_MODEL_RELOAD = frozenset({"failed", "created"})

_HARNESS_AGENT_CONFIG_FIELDS = frozenset(item.name for item in fields(HarnessAgentConfig))


def _memory_namespace(agent_id: str) -> str:
    return f"{_MEMORY_NS_PREFIX}{agent_id}"


def skills_disabled_set(cfg: dict[str, Any]) -> set[str]:
    """Return the set of disabled skill slugs from agent config."""
    raw = cfg.get("skills_disabled")
    if isinstance(raw, list):
        return {str(x) for x in raw}
    return set()


def _memory_aux_model_settings(
    mem: dict[str, Any],
    supported_fields: frozenset[str],
    is_ref_usable: Callable[[str], bool] | None,
) -> dict[str, Any]:
    """Map the ``memory.aux_model`` ref onto both harness extraction tiers.

    A stale ref (provider deleted / model disabled since it was saved) is
    dropped with a warning so extraction falls back to the default model
    instead of failing at call time.
    """
    aux_model = mem.get("aux_model")
    if (
        not isinstance(aux_model, str)
        or not aux_model.strip()
        or "memory_aux_light_model" not in supported_fields
        or "memory_aux_heavy_model" not in supported_fields
    ):
        return {}
    ref = aux_model.strip()
    if is_ref_usable is not None and not is_ref_usable(ref):
        logger.warning(
            "memory aux_model %r no longer usable; falling back to the default model",
            ref,
        )
        return {}
    # One user-chosen model drives both extraction tiers.
    return {"memory_aux_light_model": ref, "memory_aux_heavy_model": ref}


def _memory_extract_settings(
    cfg: dict[str, Any],
    *,
    supported_fields: frozenset[str] = _HARNESS_AGENT_CONFIG_FIELDS,
    is_ref_usable: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Extract the ``memory`` config section into HarnessAgentConfig kwargs.

    Mirrors the shape written by the dashboard's ``PUT .../memory/extract-config``
    endpoint. Only recognized keys are forwarded; anything missing falls through
    to HarnessAgentConfig's own defaults, so an agent with no ``memory`` section
    behaves exactly as before.
    """
    mem = cfg.get("memory")
    if not isinstance(mem, dict):
        return {}
    out: dict[str, Any] = _memory_aux_model_settings(mem, supported_fields, is_ref_usable)
    if "memory_enabled" in supported_fields and isinstance(mem.get("memory_enabled"), bool):
        out["memory_enabled"] = mem["memory_enabled"]
    if "memory_extract_on_session_end" in supported_fields and isinstance(
        mem.get("extract_on_session_end"), bool
    ):
        out["memory_extract_on_session_end"] = mem["extract_on_session_end"]
    mode = mem.get("extract_trigger_mode")
    if mode in ("idle", "interval") and "memory_extract_trigger_mode" in supported_fields:
        out["memory_extract_trigger_mode"] = mode
    for src, dst in (
        ("extract_idle_seconds", "memory_extract_idle_seconds"),
        ("extract_interval_seconds", "memory_extract_interval_seconds"),
    ):
        val = mem.get(src)
        if (
            dst in supported_fields
            and isinstance(val, int | float)
            and not isinstance(val, bool)
            and val > 0
        ):
            out[dst] = float(val)

    # orcakit-harness-agent 0.9.5 predates the interval trigger fields. Keep
    # hot reload working against that release and approximate interval mode
    # with its per-session idle watchdog until a newer harness is installed.
    if (
        mode == "interval"
        and "memory_extract_trigger_mode" not in supported_fields
        and "memory_extract_idle_seconds" in supported_fields
    ):
        interval = mem.get("extract_interval_seconds")
        if isinstance(interval, int | float) and not isinstance(interval, bool) and interval > 0:
            out["memory_extract_idle_seconds"] = float(interval)
        logger.warning(
            "Installed harness-agent lacks interval memory extraction; "
            "falling back to the idle watchdog for this agent"
        )
    return out


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class AgentCreateSpec:
    """Input for :meth:`AgentManager.create`."""

    name: str
    agent_id: str | None = None
    user_id: int | None = None
    description: str | None = None
    persona_mbti: str | None = None
    default_model: str | None = None
    system_prompt: str | None = None
    icon: str | None = None
    template_name: str | None = None
    config: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# AgentManager
# ---------------------------------------------------------------------------


class AgentManager:
    """Process-wide singleton: owns harness HarnessAgentManager + all HarnessAgent instances.

    On boot, loads all enabled agents from the DB and registers them with the
    harness HarnessAgentManager. Provides CRUD that stays in sync between DB and runtime.

    Row data is always read directly from the DB — no in-process row cache —
    so callers always see the latest persisted state.

    Public surface (by concern):
      - Lifecycle: boot / shutdown, start / stop individual agents
      - CRUD: create / update / delete
      - Reads: get_row, list_*, get_config, resolve_user_agent
      - Runtime: get_agent, stream / call / HITL / thread model
      - Hot-reload: reload*, on_provider_changed, reload_harness_agents
      - Connectors: reload_connectors*, prepare_chat_mcp
      - Settings stores: langfuse, security, acp_settings, tool_guard_rules, providers
    """

    # ------------------------------------------------------------------
    # Lifecycle — construction, wiring, boot / shutdown
    # ------------------------------------------------------------------

    def __init__(
        self,
        *,
        repos: RepoBundle,
        paths: PathLayout,
        config: OctopConfig | None = None,
        expert_catalog: ExpertCatalog | None = None,
        plugin_manager: PluginManager | None = None,
    ) -> None:
        self._repos = repos
        self._paths = paths
        from octop.config import OctopConfig as _OctopConfig  # noqa: PLC0415

        self._config = config or _OctopConfig()
        self._expert_catalog = expert_catalog
        self._plugin_manager = plugin_manager
        self._cron_manager: CronManager | None = None
        self._team_processor: Any | None = None
        self._harness_manager: HarnessAgentManager | None = None
        self._lock = asyncio.Lock()
        self._reload_dirty: set[str] = set()
        self._reload_worker_running: dict[str, bool] = {}
        self._bootstrap_graph_refresh_pending: set[str] = set()
        # Chat user id used to resolve connectors when agent.user_id is NULL (shared agents).
        self._connector_user_override: dict[str, int] = {}
        self._langfuse = LangfuseSettingsStore(
            settings_repo=repos.settings_repo,
            secret_repo=repos.secret_repo,
        )
        self._security = SecuritySettingsStore(settings_repo=repos.settings_repo)
        self._acp_settings = ACPSettingsStore(
            settings_repo=repos.settings_repo,
            agents_repo=repos.agent_repo,
        )
        self._tool_guard_rules = ToolGuardRulesStore(paths=paths)
        self._providers = ProviderStore(
            provider_repo=repos.provider_repo,
        )
        self._connector_svc = ConnectorService(
            repo=repos.connector_repo,
            secret_repo=repos.secret_repo,
            settings_repo=repos.settings_repo,
            config=self._config,
        )
        # User-scoped custom MCP tools: (user_id, server_name, fingerprint) -> tools
        self._mcp_tool_cache: dict[tuple[int, str, str], list[Any]] = {}
        self._mcp_tool_cache_locks: dict[tuple[int, str], asyncio.Lock] = {}
        self._mcp_tool_cache_guard = asyncio.Lock()

    def set_cron_manager(self, cron_manager: CronManager) -> None:
        """Attach the process-wide CronManager (must be set before boot())."""
        self._cron_manager = cron_manager

    def set_team_processor(self, team_processor: Any | None) -> None:
        """Attach harness TeamProcessor (GlobalProcessor); required before boot()."""
        self._team_processor = team_processor

    async def boot(self) -> None:
        self._tool_guard_rules.ensure_seeded()
        providers = self._providers.build_harness_configs()
        self._harness_manager = HarnessAgentManager(
            providers=providers,
            langfuse=self._langfuse.harness_config(),
            team_processor=self._team_processor,
        )
        if self._harness_manager is not None:
            self._harness_manager.set_security_policy(self._security.harness_policy())

        rows = self._repos.agent_repo.list_all(include_disabled=False)
        for row in rows:
            if row.last_state == "stopped":
                continue
            await self._start_agent(row)

    async def shutdown(self) -> None:
        async with self._lock:
            if self._harness_manager:
                try:
                    self._harness_manager.close()
                except Exception:
                    logger.exception("harness_manager.close() failed")
                self._harness_manager = None

    # ------------------------------------------------------------------
    # Exposed stores & paths (read-only accessors)
    # ------------------------------------------------------------------

    @property
    def providers(self) -> ProviderStore:
        return self._providers

    @property
    def security(self) -> SecuritySettingsStore:
        return self._security

    @property
    def acp_settings(self) -> ACPSettingsStore:
        return self._acp_settings

    @property
    def tool_guard_rules(self) -> ToolGuardRulesStore:
        return self._tool_guard_rules

    @property
    def langfuse(self) -> LangfuseSettingsStore:
        return self._langfuse

    @property
    def paths(self) -> PathLayout:
        return self._paths

    @property
    def harness_manager(self) -> HarnessAgentManager | None:
        return self._harness_manager

    # ------------------------------------------------------------------
    # CRUD — persist agent rows and sync harness runtime
    # ------------------------------------------------------------------

    async def create(self, spec: AgentCreateSpec, *, defer_bootstrap: bool = False) -> AgentRow:
        """Create a new agent, persist to DB, and register with harness."""
        async with self._lock:
            self._assert_agent_name_available(spec.user_id, spec.name)
            if spec.agent_id:
                if self._repos.agent_repo.get(spec.agent_id) is not None:
                    raise OctopError(
                        ErrorCode.AGENT_BUSY,
                        f"agent_id {spec.agent_id!r} already exists",
                    )
                agent_id = spec.agent_id
            else:
                for _ in range(16):
                    agent_id = new_short_id()
                    if self._repos.agent_repo.get(agent_id) is None:
                        break
                else:
                    raise RuntimeError("failed to allocate unique agent_id")
            config = dict(spec.config)
            if spec.persona_mbti:
                config["persona"] = spec.persona_mbti.upper()
            self._repos.agent_repo.create(
                agent_id=agent_id,
                user_id=spec.user_id,
                name=spec.name,
                description=spec.description,
                persona_mbti=spec.persona_mbti,
                default_model=spec.default_model,
                system_prompt=spec.system_prompt,
                config_json=json.dumps(config) if config else None,
                icon=spec.icon,
                template_name=spec.template_name,
            )
            row = self._repos.agent_repo.get(agent_id)
            assert row is not None
            if spec.template_name:
                await self._seed_expert_template(row, spec.template_name)
            if defer_bootstrap:
                self._repos.agent_repo.set_state(agent_id, "starting")
                asyncio.create_task(
                    self._complete_create_bootstrap(row),
                    name=f"bootstrap-agent-{agent_id}",
                )
            else:
                agent = await self._start_agent(row, init_workspace=True)
                if agent is not None and spec.template_name:
                    reload = getattr(agent, "reload_subagents", None)
                    if callable(reload):
                        await asyncio.to_thread(reload)
            self._repos.audit_repo.write(
                actor=ACTOR_SYSTEM, action="agent.create", target=agent_id, payload=spec.name
            )
            return row

    async def update(self, agent_id: str, **kwargs: Any) -> AgentRow:
        """Update agent config in DB and reload harness agent in the background."""
        new_name = kwargs.get("name")
        if isinstance(new_name, str):
            row = self._repos.agent_repo.get(agent_id)
            if row is None:
                raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
            if new_name != row.name:
                self._assert_agent_name_available(
                    row.user_id,
                    new_name,
                    exclude_agent_id=agent_id,
                )
        self._repos.agent_repo.update_config(agent_id, **kwargs)
        row = self._repos.agent_repo.get(agent_id)
        if row is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
        self._schedule_reload(agent_id)
        return row

    async def delete(self, agent_id: str) -> None:
        """Remove agent from DB, harness runtime, and workspace directory."""
        async with self._lock:
            await self._harness_manager.aremove_agent(agent_id)  # type: ignore[union-attr]
        self._repos.agent_repo.delete(agent_id)
        self._repos.audit_repo.write(actor=ACTOR_SYSTEM, action="agent.delete", target=agent_id)

    async def start(self, agent_id: str) -> None:
        """Load agent into harness runtime (no-op config merge)."""
        async with self._lock:
            row = self._repos.agent_repo.get(agent_id)
            if row is None:
                raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
            await self._start_agent(row, init_workspace=False)

    async def stop(self, agent_id: str) -> None:
        """Unload agent from harness runtime and persist ``last_state=stopped``."""
        async with self._lock:
            row = self._repos.agent_repo.get(agent_id)
            if row is None:
                raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
            await self._harness_manager.aremove_agent(agent_id)  # type: ignore[union-attr]
            self._repos.agent_repo.set_state(agent_id, "stopped", error=None)

    # ------------------------------------------------------------------
    # Row & config reads — DB lookups, no harness required
    # ------------------------------------------------------------------

    def get_row(self, agent_id: str) -> AgentRow | None:
        """Look up an agent row by its public agent_id (ULID). Returns None if absent."""
        return self._repos.agent_repo.get(agent_id)

    def workspace_for_agent(self, agent_id: str) -> Any | None:
        """Resolve :class:`BackendWorkspace` without a running harness agent."""
        row = self.get_row(agent_id)
        if row is None:
            return None
        return self._backend_workspace_for_row(row)

    def list_agents(self, user_id: int) -> list[AgentRow]:
        return self._repos.agent_repo.list_by_user(user_id, include_disabled=False)

    def list_rows(self) -> list[AgentRow]:
        """Return all enabled agent rows (all users), sorted by creation time."""
        return self._repos.agent_repo.list_all(include_disabled=False)

    def resolve_user_agent(self, user_id: int, query: str) -> AgentRow | None:
        """Match an agent owned by *user_id* by id suffix, full id, or name."""
        q = query.strip()
        if not q:
            return None
        rows = self.list_agents(user_id)
        ql = q.lower()
        for row in rows:
            if row.agent_id == q or row.agent_id.endswith(q):
                return row
        for row in rows:
            if row.name.lower() == ql:
                return row
        partial = [r for r in rows if ql in r.name.lower()]
        return partial[0] if len(partial) == 1 else None

    def get_config(self, agent_id: str) -> dict[str, Any]:
        """Return the parsed config_json for agent_id, or empty dict."""
        row = self._repos.agent_repo.get(agent_id)
        if row is None:
            return {}
        try:
            cfg = json.loads(row.config_json or "{}")
            return cfg if isinstance(cfg, dict) else {}
        except Exception:
            return {}

    def is_bootstrapped(self, agent_id: str) -> bool:
        """Whether onboarding has completed for a running agent."""
        try:
            return self.get_agent(agent_id).is_bootstrapped()
        except OctopError:
            return False

    def find_agents_using_provider(self, provider_name: str) -> list[dict[str, str]]:
        """Return agents referencing *provider_name* in config or default_model."""
        return self._providers.find_agents_using_provider(
            agent_repo=self._repos.agent_repo,
            get_config=self.get_config,
            provider_name=provider_name,
        )

    # ------------------------------------------------------------------
    # Runtime access — live HarnessAgent handle
    # ------------------------------------------------------------------

    def get_agent(self, agent_id: str) -> HarnessAgent:
        """Return the live HarnessAgent for agent_id (ULID).

        Raises OctopError.AGENT_NOT_FOUND if not running.
        """
        if self._harness_manager is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not running")
        try:
            return self._harness_manager.get_agent(agent_id).agent
        except KeyError:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not running") from None

    # ------------------------------------------------------------------
    # Chat / invoke — stream, call, HITL, thread model overrides
    # ------------------------------------------------------------------

    async def stream(self, agent_id: str, request: dict[str, Any]) -> AsyncIterator[Any]:
        """Stream harness chunks (Langfuse tracing handled inside harness-agent)."""
        if self._harness_manager is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not running")

        self._apply_pending_bootstrap_graph_refresh(agent_id)
        req = self._prepare_stream_request(agent_id, request)
        async for chunk in self._harness_manager.stream(agent_id, cast(Any, req)):
            yield chunk
        self._apply_pending_bootstrap_graph_refresh(agent_id)

    async def call(self, agent_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Non-streaming harness invocation (one-shot agent call)."""
        if self._harness_manager is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not running")
        self._apply_pending_bootstrap_graph_refresh(agent_id)
        req = self._prepare_stream_request(agent_id, request)
        result = await self._harness_manager.call(agent_id, cast(Any, req))
        self._apply_pending_bootstrap_graph_refresh(agent_id)
        if not isinstance(result, dict):
            return {"result": result}
        return result

    async def resume_hitl(
        self,
        agent_id: str,
        thread_id: str,
        decisions: list[dict[str, Any]],
    ) -> AsyncIterator[Any]:
        """Resume a paused HITL interrupt for *thread_id*."""
        if self._harness_manager is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not running")
        self._apply_pending_bootstrap_graph_refresh(agent_id)
        async for chunk in self._harness_manager.resume_hitl(agent_id, thread_id, decisions):
            yield chunk
        self._apply_pending_bootstrap_graph_refresh(agent_id)

    def cancel_stream(self, agent_id: str, thread_id: str) -> None:
        """Signal harness-agent to stop the active stream for *(agent_id, thread_id)*."""
        if self._harness_manager is not None:
            self._harness_manager.cancel(agent_id, thread_id)

    def get_thread_model(self, agent_id: str, thread_id: str) -> str | None:
        if self._harness_manager is None:
            return None
        return self._harness_manager.get_thread_model(agent_id, thread_id)

    def set_thread_model(self, agent_id: str, thread_id: str, model: str) -> None:
        if self._harness_manager is not None:
            self._harness_manager.set_thread_model(agent_id, thread_id, model)

    def clear_thread_model(self, agent_id: str, thread_id: str) -> None:
        if self._harness_manager is not None:
            self._harness_manager.clear_thread_model(agent_id, thread_id)

    # ------------------------------------------------------------------
    # Hot-reload — rebuild harness agents after config / provider changes
    # ------------------------------------------------------------------

    async def reload(self, agent_id: str) -> None:
        """Rebuild harness runtime for one agent (e.g. after plugin install)."""
        await self._reload_agent(agent_id)

    async def reload_all(self) -> None:
        """Rebuild harness runtime for every enabled agent (bounded parallel)."""
        agent_ids = [
            row.agent_id for row in self._repos.agent_repo.list_all(include_disabled=False)
        ]
        await self._reload_agents(agent_ids)

    def reload_harness_agents(self) -> None:
        """Rebuild harness agents in place (e.g. after tool-guard rules changed on disk).

        Does not rebuild Octop-side agent config from the DB — use :meth:`reload` for that.
        """
        if self._harness_manager is not None:
            self._harness_manager.rebuild_all_agents()

    def _agent_uses_auto_default(self, row: AgentRow) -> bool:
        cfg = self.get_config(row.agent_id)
        return self._providers.resolve_explicit_default_model(row, cfg) is None

    def _provider_reload_impact_ids(
        self,
        *,
        provider_name: str | None = None,
        active_model_changed: bool = False,
    ) -> list[str]:
        """Agent IDs that must be rebuilt after a provider / active-model change."""
        rows = self._repos.agent_repo.list_all(include_disabled=False)
        if provider_name is None and not active_model_changed:
            return [row.agent_id for row in rows]

        enabled_ids = {row.agent_id for row in rows}
        impact: set[str] = set()
        include_auto = active_model_changed
        if provider_name and not include_auto:
            active_name, _ = self._repos.settings_repo.get_active_model()
            include_auto = active_name == provider_name

        for row in rows:
            if row.last_state in _AGENT_STATES_NEEDING_MODEL_RELOAD or (
                include_auto and self._agent_uses_auto_default(row)
            ):
                impact.add(row.agent_id)

        if provider_name:
            for ref in self.find_agents_using_provider(provider_name):
                aid = ref.get("agent_id")
                if isinstance(aid, str) and aid in enabled_ids:
                    impact.add(aid)

        return sorted(impact)

    async def _reload_agents(self, agent_ids: list[str]) -> None:
        """Reload agents concurrently with a fixed concurrency cap."""
        if not agent_ids:
            return
        sem = asyncio.Semaphore(_PROVIDER_RELOAD_CONCURRENCY)

        async def _one(agent_id: str) -> None:
            async with sem:
                try:
                    await self._reload_agent(agent_id)
                except Exception:
                    logger.exception("Parallel reload failed for agent %s", agent_id)

        await asyncio.gather(*(_one(agent_id) for agent_id in agent_ids))

    async def on_provider_changed(
        self,
        *,
        provider_name: str | None = None,
        active_model_changed: bool = False,
    ) -> None:
        """Sync harness factory from DB, then reload impacted agents (awaited).

        When *provider_name* or *active_model_changed* is set, only the impact set
        is rebuilt. With neither set (backup restore, OAuth, unknown), all enabled
        agents are rebuilt in parallel.
        """
        if self._harness_manager is None:
            return
        providers = self._providers.build_harness_configs()
        sync_providers_to_harness(
            self._harness_manager,
            providers,
            shared_factory=self._harness_manager.shared_factory,
        )
        if self._harness_manager.shared_factory is None:
            return
        await self._reload_agents(
            self._provider_reload_impact_ids(
                provider_name=provider_name,
                active_model_changed=active_model_changed,
            )
        )

    # ------------------------------------------------------------------
    # Connectors & MCP — OAuth refresh and pre-chat tool loading
    # ------------------------------------------------------------------

    async def reload_connectors(
        self,
        agent_id: str,
        *,
        connector_user_id: int | None = None,
    ) -> None:
        """Refresh connector OAuth tokens and reload harness MCP tool registrations."""
        row = self.get_row(agent_id)
        if row is None:
            return
        uid = self._connector_uid_for(row, connector_user_id=connector_user_id)
        if uid is None:
            logger.warning(
                "agent %s: skip connector reload — agent.user_id is NULL and no connector_user_id",
                agent_id,
            )
            return
        self._connector_user_override[agent_id] = uid
        try:
            svc = self._connector_svc
            for inst in self._repos.connector_repo.list_by_user(uid):
                if inst.status != "active":
                    continue
                await svc.ensure_fresh_credentials(inst.instance_id, inst.kind)
            await self._reload_agent(agent_id)
        finally:
            self._connector_user_override.pop(agent_id, None)

    async def reload_connectors_for_user(self, user_id: int) -> None:
        self.invalidate_mcp_tool_cache(user_id)
        reloaded: set[str] = set()
        for row in self._repos.agent_repo.list_by_user(user_id, include_disabled=False):
            await self.reload_connectors(row.agent_id, connector_user_id=user_id)
            reloaded.add(row.agent_id)
        # Shared agents (user_id IS NULL) still need this user's connector MCP configs.
        for row in self._repos.agent_repo.list_all(include_disabled=False):
            if row.user_id is not None or row.agent_id in reloaded:
                continue
            await self.reload_connectors(row.agent_id, connector_user_id=user_id)

    def invalidate_mcp_tool_cache(self, user_id: int | None = None) -> None:
        """Drop cached custom MCP tools (one user, or all users when ``user_id`` is None)."""
        if user_id is None:
            self._mcp_tool_cache.clear()
            self._mcp_tool_cache_locks.clear()
            return
        for cache_key in [k for k in self._mcp_tool_cache if k[0] == user_id]:
            del self._mcp_tool_cache[cache_key]
        for lock_key in [k for k in self._mcp_tool_cache_locks if k[0] == user_id]:
            del self._mcp_tool_cache_locks[lock_key]

    async def _server_lock(self, user_id: int, server_name: str) -> asyncio.Lock:
        key = (user_id, server_name)
        async with self._mcp_tool_cache_guard:
            lock = self._mcp_tool_cache_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._mcp_tool_cache_locks[key] = lock
            return lock

    async def _get_or_load_mcp_tools(
        self,
        user_id: int,
        server_name: str,
        spec: dict[str, Any],
    ) -> list[Any]:
        """Load custom MCP tools once per user/server/fingerprint; share across agents."""
        from harness_agent.mcp import aload_mcp_tools

        from octop.infra.connectors.mcp_tool_cache import (
            fingerprint_mcp_spec,
            wrap_tools_for_shared_use,
        )

        fp = fingerprint_mcp_spec(spec)
        cache_key = (user_id, server_name, fp)
        cached = self._mcp_tool_cache.get(cache_key)
        if cached is not None:
            return cached

        async with self._mcp_tool_cache_guard:
            cached = self._mcp_tool_cache.get(cache_key)
            if cached is not None:
                return cached
            load_lock = self._mcp_tool_cache_locks.get((user_id, server_name))
            if load_lock is None:
                load_lock = asyncio.Lock()
                self._mcp_tool_cache_locks[(user_id, server_name)] = load_lock

        async with load_lock:
            cached = self._mcp_tool_cache.get(cache_key)
            if cached is not None:
                return cached
            raw = await aload_mcp_tools({server_name: spec})
            server_lock = await self._server_lock(user_id, server_name)
            wrapped = wrap_tools_for_shared_use(raw, server_lock)
            self._mcp_tool_cache[cache_key] = wrapped
            stale = [
                key
                for key in self._mcp_tool_cache
                if key[0] == user_id and key[1] == server_name and key[2] != fp
            ]
            for key in stale:
                del self._mcp_tool_cache[key]
            logger.info(
                "mcp tool cache store user=%s server=%s fingerprint=%s tools=%d",
                user_id,
                server_name,
                fp,
                len(wrapped),
            )
            return wrapped

    async def prepare_chat_mcp(
        self,
        agent_id: str,
        names: list[str] | None,
        *,
        connector_user_id: int | None = None,
    ) -> list[str]:
        """Ensure requested MCP servers are configured and tools are loaded before chat.

        Custom MCP tools are loaded on demand and shared via a user-level cache.
        Built-in connectors still use reload_connectors when missing.

        Returns server names that still have no loaded tools after reload/retry.
        """
        if not names:
            return []
        agent = self.get_agent(agent_id)
        row = self.get_row(agent_id)
        uid = self._connector_uid_for(row, connector_user_id=connector_user_id) if row else None
        if uid is None and connector_user_id is not None:
            uid = connector_user_id

        tool_set: frozenset[str] = getattr(agent, "_mcp_tool_name_set", frozenset())
        missing_tools = [n for n in names if not any(t.startswith(f"{n}_") for t in tool_set)]
        logger.info(
            "prepare_chat_mcp agent=%s connector_user_id=%s requested=%s tool_count=%d missing=%s",
            agent_id,
            connector_user_id,
            names,
            len(tool_set),
            missing_tools,
        )
        if not missing_tools:
            matched = sorted(t for t in tool_set if any(t.startswith(f"{n}_") for n in names))
            logger.info(
                "prepare_chat_mcp agent=%s: MCP already ready, matching_tools=%s",
                agent_id,
                matched,
            )
            return []

        custom_configs: dict[str, Any] = {}
        if uid is not None:
            custom_configs = self._connector_svc.custom_harness_configs(uid)

        custom_missing = [n for n in missing_tools if n in custom_configs]
        builtin_missing = [n for n in missing_tools if n not in custom_configs]

        if custom_missing and uid is not None:
            for name in custom_missing:
                spec = custom_configs[name]
                if not isinstance(spec, dict) or not spec.get("transport"):
                    continue
                try:
                    tools = await self._get_or_load_mcp_tools(uid, name, spec)
                except Exception:
                    logger.exception(
                        "prepare_chat_mcp agent=%s: failed loading custom MCP %s",
                        agent_id,
                        name,
                    )
                    continue
                if tools:
                    try:
                        agent.append_mcp_tools(tools)
                    except Exception:
                        logger.exception(
                            "prepare_chat_mcp agent=%s: append_mcp_tools failed for %s",
                            agent_id,
                            name,
                        )
                        continue
                agent.config.mcp_server_configs[name] = dict(spec)

        if builtin_missing:
            logger.info(
                "Reloading agent %s MCP tools (builtin_missing=%s)",
                agent_id,
                builtin_missing,
            )
            await self.reload_connectors(agent_id, connector_user_id=connector_user_id)
            agent = self.get_agent(agent_id)
            tool_set = getattr(agent, "_mcp_tool_name_set", frozenset())
            still_builtin = [
                n
                for n in builtin_missing
                if n in agent.config.mcp_server_configs
                and not any(t.startswith(f"{n}_") for t in tool_set)
            ]
            still_builtin.extend(
                n for n in builtin_missing if n not in agent.config.mcp_server_configs
            )
            still_builtin = sorted(set(still_builtin))
            if still_builtin:
                from harness_agent.mcp import aload_mcp_tools

                subset = {
                    n: agent.config.mcp_server_configs[n]
                    for n in still_builtin
                    if isinstance(agent.config.mcp_server_configs.get(n), dict)
                    and agent.config.mcp_server_configs[n].get("transport")
                }
                if subset:
                    logger.info(
                        "prepare_chat_mcp agent=%s: targeted MCP reload for %s",
                        agent_id,
                        sorted(subset),
                    )
                    extra = await aload_mcp_tools(subset)
                    if extra:
                        agent.append_mcp_tools(extra)

            # Full reload drops previously appended custom tools — re-inject from cache.
            if custom_configs and uid is not None:
                agent = self.get_agent(agent_id)
                tool_set = getattr(agent, "_mcp_tool_name_set", frozenset())
                for name in names:
                    if name not in custom_configs:
                        continue
                    if any(t.startswith(f"{name}_") for t in tool_set):
                        continue
                    spec = custom_configs[name]
                    if not isinstance(spec, dict) or not spec.get("transport"):
                        continue
                    try:
                        tools = await self._get_or_load_mcp_tools(uid, name, spec)
                    except Exception:
                        logger.exception(
                            "prepare_chat_mcp agent=%s: re-inject custom MCP %s failed",
                            agent_id,
                            name,
                        )
                        continue
                    if tools:
                        agent.append_mcp_tools(tools)
                        agent.config.mcp_server_configs[name] = dict(spec)
                    tool_set = getattr(agent, "_mcp_tool_name_set", frozenset())

        agent = self.get_agent(agent_id)
        tool_set = getattr(agent, "_mcp_tool_name_set", frozenset())
        still_missing = sorted(n for n in names if not any(t.startswith(f"{n}_") for t in tool_set))
        if still_missing:
            logger.warning(
                "prepare_chat_mcp agent=%s: tools still missing for %s",
                agent_id,
                still_missing,
            )
        return still_missing

    # ------------------------------------------------------------------
    # Settings persistence — push global policy into harness runtime
    # ------------------------------------------------------------------

    def save_langfuse(
        self,
        *,
        enabled: bool,
        public_key: str,
        host: str,
        secret_key: str | None = None,
    ) -> LangfuseSettings:
        """Persist Langfuse settings and push them into the harness runtime."""
        view = self._langfuse.save(
            enabled=enabled,
            public_key=public_key,
            host=host,
            secret_key=secret_key,
        )
        if self._harness_manager is not None:
            self._harness_manager.set_langfuse(self._langfuse.harness_config())
        return view

    def save_security(self, policy: SecurityPolicy | dict[str, Any]) -> SecurityPolicy:
        """Persist security policy and push it into harness agents."""
        resolved = self._security.save(policy)
        if self._harness_manager is not None:
            try:
                self._harness_manager.set_security_policy(self._security.harness_policy())
            except Exception:
                logger.exception("failed to apply security policy to running harness agents")
        return resolved

    # ------------------------------------------------------------------
    # Agent config mutations — persona, skills, config_json patches
    # ------------------------------------------------------------------

    async def apply_persona_mbti(self, agent_id: str, code: str) -> AgentRow:
        """Persist MBTI persona on the agent row and reload harness runtime."""
        norm = code.upper()
        row = self._repos.agent_repo.get(agent_id)
        if row is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")

        from octop.infra.agents.persona import PersonaLoader  # noqa: PLC0415

        loader = PersonaLoader()
        persona_text = loader.render(
            mbti=norm,
            agent_name=row.name,
            user_display="User",
            custom=None,
        )

        cfg = self.get_config(agent_id)
        cfg["persona"] = norm
        self._repos.agent_repo.update_config(
            agent_id,
            persona_mbti=norm,
            system_prompt=persona_text,
            config_json=json.dumps(cfg),
        )
        row = self._repos.agent_repo.get(agent_id)
        if row is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
        self._schedule_reload(agent_id)
        return row

    async def update_config_json(self, agent_id: str, config_json: str) -> AgentRow:
        """Patch ``config_json`` and reload the harness runtime in the background."""
        self._repos.agent_repo.update_config(agent_id, config_json=config_json)
        row = self._repos.agent_repo.get(agent_id)
        if row is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id!r} not found")
        self._schedule_reload(agent_id)
        return row

    async def list_skill_summaries(self, agent_id: str) -> list[dict[str, Any]]:
        """Installed skills for *agent_id* (delegates to harness-agent catalog)."""
        agent = self.get_agent(agent_id)
        return await agent.list_skill_summaries()

    def list_subagent_summaries(self, agent_id: str) -> list[dict[str, Any]]:
        """Installed subagents for *agent_id* (delegates to harness-agent catalog)."""
        agent = self.get_agent(agent_id)
        return agent.list_subagent_summaries()

    def sync_skills_disabled(self, agent_id: str, disabled: set[str]) -> None:
        """Push ``skills_disabled`` to the running harness agent (hot update)."""
        self.get_agent(agent_id).set_skills_disabled(disabled)

    # ------------------------------------------------------------------
    # Internal — validation
    # ------------------------------------------------------------------

    def _assert_agent_name_available(
        self,
        user_id: int | None,
        name: str,
        *,
        exclude_agent_id: str | None = None,
    ) -> None:
        if user_id is None:
            return
        for row in self._repos.agent_repo.list_by_user(user_id):
            if row.name == name and row.agent_id != exclude_agent_id:
                raise OctopError(
                    ErrorCode.AGENT_NAME_TAKEN,
                    f"agent name {name!r} already in use",
                )

    # ------------------------------------------------------------------
    # Internal — agent startup & workspace seeding
    # ------------------------------------------------------------------

    async def _complete_create_bootstrap(self, row: AgentRow) -> None:
        """Start harness runtime after create (expert files are already seeded on disk)."""
        try:
            fresh = self._repos.agent_repo.get(row.agent_id)
            if fresh is None:
                return
            agent = await self._start_agent(fresh, init_workspace=True)
            if agent is not None and fresh.template_name:
                reload = getattr(agent, "reload_subagents", None)
                if callable(reload):
                    await asyncio.to_thread(reload)
        except Exception:
            logger.exception("Deferred bootstrap failed for agent %s", row.agent_id)

    async def _start_agent(
        self, row: AgentRow, *, init_workspace: bool = True
    ) -> HarnessAgent | None:
        assert self._harness_manager is not None, "_start_agent called before boot()"
        if self._harness_manager.shared_factory is None:
            self._repos.agent_repo.set_state(row.agent_id, "failed", error=NO_MODELS_CONFIGURED)
            return None
        try:
            cfg, metadata, tags, user_display = self._agent_runtime_bundle(row)
            entry = await self._harness_manager.acreate_agent(
                cfg,
                agent_id=row.agent_id,
                metadata=metadata,
                tags=tags,
                init_workspace=init_workspace,
            )
            await self._post_start_agent(row, entry.agent, cfg, user_display=user_display)
            self._repos.agent_repo.set_state(row.agent_id, "running")
            logger.info("Agent %s (%s) started", row.agent_id, row.name)
            return entry.agent
        except Exception as exc:
            logger.exception("Failed to start agent %s", row.agent_id)
            self._repos.agent_repo.set_state(
                row.agent_id,
                "failed",
                error=format_agent_start_error(exc),
            )
            return None

    async def _post_start_agent(
        self,
        row: AgentRow,
        agent: HarnessAgent,
        cfg: HarnessAgentConfig,
        *,
        user_display: str = "User",
    ) -> None:
        uid = self._connector_uid_for(row)
        if uid is not None:
            inject_missing_gateway_tools(
                agent,
                svc=self._connector_svc,
                connector_repo=self._repos.connector_repo,
                user_id=uid,
                agent_id=row.agent_id,
                mcp_server_configs=cfg.mcp_server_configs,
            )
        tool_set: frozenset[str] = getattr(agent, "_mcp_tool_name_set", frozenset())
        logger.info(
            "Agent %s started with mcp_servers=%s mcp_tool_count=%d tools_sample=%s",
            row.agent_id,
            sorted(agent.config.mcp_server_configs.keys()),
            len(tool_set),
            sorted(tool_set)[:8],
        )
        ws = agent.workspace
        if self._plugin_manager is not None:
            await asyncio.to_thread(self._plugin_manager.sync_skills_to_workspace, ws)

        # Patch config when bootstrap finishes, but defer graph recompile until
        # the in-flight turn has fully drained (sync _init_graph mid-stream segfaults).
        if not agent.is_bootstrapped():
            agent_id = row.agent_id

            def _on_bootstrap_complete() -> None:
                self._mark_bootstrap_graph_refresh_pending(agent_id, agent)

            agent.on_bootstrap_complete = _on_bootstrap_complete

    def _mark_bootstrap_graph_refresh_pending(self, agent_id: str, agent: HarnessAgent) -> None:
        """Record DB-backed config updates; graph rebuild runs on the next turn."""
        row = self._repos.agent_repo.get(agent_id)
        if row is None:
            return
        agent._config.system_prompt = row.system_prompt
        if agent._config.memory == ():
            agent._config.memory = None
        self._bootstrap_graph_refresh_pending.add(agent_id)
        logger.info(
            "Bootstrap complete for agent %s — graph refresh deferred to next turn",
            agent_id,
        )

    def _apply_pending_bootstrap_graph_refresh(self, agent_id: str) -> None:
        """Recompile harness graph after bootstrap once no stream is in progress."""
        if agent_id not in self._bootstrap_graph_refresh_pending:
            return
        if self._harness_manager is None:
            return
        try:
            entry = self._harness_manager.get_agent(agent_id)
        except KeyError:
            return
        self._bootstrap_graph_refresh_pending.discard(agent_id)
        try:
            entry.agent._init_graph()
            logger.info("Bootstrap graph refresh applied for agent %s", agent_id)
        except Exception:
            logger.exception("Bootstrap graph refresh failed for agent %s", agent_id)
            self._bootstrap_graph_refresh_pending.add(agent_id)

    def _agent_config_dict(self, row: AgentRow) -> dict[str, Any]:
        try:
            cfg = json.loads(row.config_json or "{}")
            if not isinstance(cfg, dict):
                return {}
        except Exception:
            return {}
        return cfg

    def _backend_spec_for_row(self, row: AgentRow) -> Any:
        cfg = self._agent_config_dict(row)
        backend_spec = cfg.get("backend")
        if backend_spec is None:
            workspace_dir = self._paths.ensure_agent_workspace(row.agent_id)
            return default_agent_backend_spec(workspace_dir)
        return resolve_agent_backend_spec(
            backend_spec,
            repo=self._repos.storage_backend_repo,
        )

    def _backend_workspace_for_row(self, row: AgentRow) -> Any:
        """Resolve :class:`BackendWorkspace` for *row* without a running harness agent."""
        from harness_agent.backends import resolve_backend  # noqa: PLC0415
        from harness_agent.backends.workspace import BackendWorkspace  # noqa: PLC0415

        workspace_dir = self._paths.ensure_agent_workspace(row.agent_id)
        backend = self._backend_spec_for_row(row)
        return BackendWorkspace(
            resolve_backend(backend, workspace_dir=workspace_dir), workspace_dir
        )

    async def _seed_expert_template(self, row: AgentRow, template_name: str) -> None:
        """Copy bundled expert files into the agent workspace before harness start."""
        if self._expert_catalog is None:
            logger.warning(
                "Agent %s: template_name=%r set but no expert_catalog configured; skipping",
                row.agent_id,
                template_name,
            )
            return

        expert = self._expert_catalog.get(template_name)
        if expert is None:
            logger.warning(
                "Agent %s: expert %r not found in catalog; skipping template copy",
                row.agent_id,
                template_name,
            )
            return

        from octop.infra.agents.experts.catalog import (  # noqa: PLC0415
            MANIFEST_FILENAME,
            seed_expert_directory,
        )

        expert_dir = self._expert_catalog.expert_dir(template_name)
        if not expert.files and not (expert_dir / MANIFEST_FILENAME).is_file():
            return

        workspace = self._backend_workspace_for_row(row)
        try:
            count = await seed_expert_directory(
                expert_dir=expert_dir,
                workspace=workspace,
                seed_paths=expert.files,
            )
        except Exception as exc:
            logger.warning(
                "Agent %s: expert template %r seed failed: %s",
                row.agent_id,
                template_name,
                exc,
            )
            return
        logger.info(
            "Agent %s: seeded expert template %r (%d files)",
            row.agent_id,
            template_name,
            count,
        )

    # ------------------------------------------------------------------
    # Internal — background reload worker
    # ------------------------------------------------------------------

    async def _reload_agent(self, agent_id: str) -> None:
        assert self._harness_manager is not None
        self._bootstrap_graph_refresh_pending.discard(agent_id)
        row = self._repos.agent_repo.get(agent_id)
        if not row or not row.enabled or row.last_state == "stopped":
            await self._harness_manager.aremove_agent(agent_id)
            return
        if self._harness_manager.shared_factory is None:
            return
        try:
            cfg, metadata, tags, user_display = self._agent_runtime_bundle(row)
            entry = await self._harness_manager.arebuild_agent(
                agent_id,
                cfg,
                metadata=metadata,
                tags=tags,
            )
            await self._post_start_agent(row, entry.agent, cfg, user_display=user_display)
            self._repos.agent_repo.set_state(agent_id, "running", error=None)
        except Exception as exc:
            logger.exception("Background reload failed for agent %s", agent_id)
            self._repos.agent_repo.set_state(
                agent_id,
                "failed",
                error=format_agent_start_error(exc),
            )

    def _schedule_reload(self, agent_id: str) -> None:
        """Queue a background harness reload; coalesces rapid successive updates."""
        self._reload_dirty.add(agent_id)
        if self._reload_worker_running.get(agent_id):
            return
        self._reload_worker_running[agent_id] = True
        asyncio.create_task(self._reload_worker(agent_id), name=f"reload-agent-{agent_id}")

    async def _reload_worker(self, agent_id: str) -> None:
        try:
            while agent_id in self._reload_dirty:
                self._reload_dirty.discard(agent_id)
                try:
                    await self._reload_agent(agent_id)
                except Exception:
                    logger.exception("Background reload failed for agent %s", agent_id)
                if agent_id not in self._reload_dirty:
                    break
        finally:
            self._reload_worker_running[agent_id] = False
            if agent_id in self._reload_dirty:
                self._schedule_reload(agent_id)

    # ------------------------------------------------------------------
    # Internal — harness config assembly & stream request prep
    # ------------------------------------------------------------------

    def _agent_runtime_bundle(
        self, row: AgentRow
    ) -> tuple[HarnessAgentConfig, dict[str, Any], list[str], str]:
        from octop.infra.utils.browser_media import (  # noqa: PLC0415
            agent_outbound_screenshots_dir,
            configure_browser_screenshots_dir,
        )

        configure_browser_screenshots_dir(
            agent_outbound_screenshots_dir(self._paths, row.agent_id),
        )
        user_display = "User"
        if row.user_id is not None:
            owner = self._repos.user_repo.get(row.user_id)
            if owner is not None:
                user_display = owner.display_name or owner.username or user_display
        cfg = self._build_harness_config(row)
        metadata: dict[str, Any] = {
            "user_id": row.user_id,
            "description": row.description,
            "icon": row.icon,
            "template_name": row.template_name,
        }
        tags: list[str] = []
        if row.template_name:
            tags.append(row.template_name)
        return cfg, metadata, tags, user_display

    def _connector_uid_for(
        self,
        row: AgentRow,
        *,
        connector_user_id: int | None = None,
    ) -> int | None:
        override = self._connector_user_override.get(row.agent_id)
        if override is not None:
            return override
        if connector_user_id is not None:
            return connector_user_id
        return row.user_id

    def _prepare_stream_request(self, agent_id: str, request: dict[str, Any]) -> dict[str, Any]:
        from harness_agent.plugins import collect_plugin_tool_configs  # noqa: PLC0415

        req = dict(request)
        if req.get("agent_id") is None:
            req["agent_id"] = agent_id
        agent_cfg = self.get_config(agent_id)
        plugins_cfg = agent_cfg.get("plugins")
        tool_configs = collect_plugin_tool_configs(
            plugins_cfg if isinstance(plugins_cfg, dict) else None
        )
        if tool_configs:
            configurable = dict(req.get("configurable") or {})
            configurable["plugin_tool_configs"] = tool_configs
            req["configurable"] = configurable
        return req

    def _build_harness_config(self, row: AgentRow) -> HarnessAgentConfig:
        """Convert an AgentRow into a HarnessAgentConfig."""
        from harness_agent.middleware.bootstrap import bootstrap_marker_exists  # noqa: PLC0415

        workspace_dir = self._paths.ensure_agent_workspace(row.agent_id)
        cfg = self._agent_config_dict(row)

        backend = self._backend_spec_for_row(row)
        ws = self._backend_workspace_for_row(row)

        cron_tools: list[Any] | None = None
        if self._cron_manager is not None:
            from octop.infra.cron.tools import build_cronjob_tools  # noqa: PLC0415

            cron_tools = build_cronjob_tools(self._cron_manager)

        from harness_agent.plugins import PluginRegistry, build_plugin_tools  # noqa: PLC0415

        agent_plugins = cfg.get("plugins") if isinstance(cfg.get("plugins"), dict) else {}
        global_plugins = (
            self._plugin_manager.global_enabled_map() if self._plugin_manager is not None else {}
        )
        plugin_tools = build_plugin_tools(
            agent_plugins=agent_plugins,
            global_plugins=global_plugins,
        )
        plugin_middleware = PluginRegistry().build_middleware_chain(global_enabled=global_plugins)
        from octop.infra.agents.middleware.binary_read_guard import BinaryReadGuardMiddleware

        agent_middleware = [*plugin_middleware, BinaryReadGuardMiddleware()]

        merged_tools: list[Any] = []
        if cron_tools:
            merged_tools.extend(cron_tools)
        merged_tools.extend(plugin_tools)
        if self._harness_manager is not None:
            merged_tools.extend(self._harness_manager.team.team_tools())

        acp_section = cfg.get("acp")
        acp_raw: dict[str, Any] = acp_section if isinstance(acp_section, dict) else {}
        from harness_agent.acp.models import ACPConfig

        acp_user_id = row.user_id
        if acp_user_id is None:
            acp_user_id = self._connector_user_override.get(row.agent_id)
        runners_dict = (
            self._acp_settings.load_runners(acp_user_id) if acp_user_id is not None else {}
        )
        acp_config = ACPConfig.from_dict({"runners": runners_dict})

        system_prompt = row.system_prompt
        memory: tuple[str, ...] | None = None
        if not bootstrap_marker_exists(ws):
            system_prompt = None
            memory = ()

        uid = self._connector_uid_for(row)
        mcp_server_configs: dict[str, Any] = {}
        if uid is not None:
            mcp_server_configs = build_mcp_server_configs_for_user(
                svc=self._connector_svc,
                connector_repo=self._repos.connector_repo,
                user_id=uid,
                agent_id=row.agent_id,
                agent_user_id=row.user_id,
                config=self._config,
            )
        elif row.user_id is None:
            logger.warning(
                "_build_harness_config agent=%s agent.user_id=NULL and no connector_user_override — "
                "mcp_server_configs will be empty (shared agent needs chat user id)",
                row.agent_id,
            )

        harness_cfg = HarnessAgentConfig(
            name=_memory_namespace(row.agent_id),
            workspace_dir=workspace_dir,
            # Memory aux LLM (extraction / promotion) needs a concrete ref; fall
            # back to the first usable model — the same one AUTO chat routing
            # resolves to — so promotion works whenever chat does. Per-turn AUTO
            # routing is unaffected: the gateway resolves models via
            # ``resolve_explicit_default_model`` directly.
            default_model=(
                self._providers.resolve_explicit_default_model(row, cfg)
                or self._providers.resolve_first_model_ref()
            ),
            system_prompt=system_prompt,
            memory=memory,
            backend=backend,  # resolved spec; harness re-resolves to a runtime instance
            mcp_server_configs=mcp_server_configs,
            tools=merged_tools or None,
            middleware=agent_middleware or None,
            bootstrap_enabled=True,
            acp_runners=acp_config.runners,
            acp_delegate_enabled=bool(acp_raw.get("tool_enabled", False)),
            skills_disabled=frozenset(skills_disabled_set(cfg)),
            default_timezone=self._config.default_timezone,
            **_memory_extract_settings(cfg, is_ref_usable=self._providers.is_model_ref_usable),
        )
        global_policy = self._security.harness_policy()
        agent_override = cfg.get("security") if isinstance(cfg.get("security"), dict) else None
        policy = SecurityPolicy.merge(global_policy, agent_override)
        applied = policy.apply_to_config(harness_cfg)
        if backend_spec_supports_execution(applied.backend) and applied.permissions:
            logger.debug(
                "Omitting filesystem permissions for agent %s: backend supports shell execution",
                row.agent_id,
            )
            applied = replace(applied, permissions=None)
        return replace(
            applied,
            tool_guard_rules_dir=str(self._tool_guard_rules.rules_dir),
        )
