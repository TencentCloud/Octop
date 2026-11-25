"""Cron delivery orchestration, separate from channel transport."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, HumanMessage

from octop.i18n import tr
from octop.infra.agents.security.hitl_session import HitlSessionPolicy, ephemeral_hitl_policy
from octop.infra.agents.turn_resources import attach_turn_knowledge, resolve_turn_mcp
from octop.infra.cron.script_run import ScriptRunError, run_cron_script
from octop.infra.cron.session_target import pinned_thread_id
from octop.infra.cron.task_type import CronTaskType, normalize_cron_task_type
from octop.infra.db.repos.threads import ThreadRow
from octop.infra.gateway.process import build_harness_request
from octop.infra.gateway.process.message_keys import COMPOSER_CTX_KEY, build_composer_context
from octop.infra.gateway.process.usage_record import (
    TurnMeter,
    UsageTracker,
    record_turn_usage,
)
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.history.projection import TurnHistoryTracker, message_inputs
from octop.infra.utils.llm_text import strip_thinking
from octop.infra.utils.locale import resolve_user_locale
from octop.infra.utils.turn_failure import log_failed_tool_results
from octop.infra.utils.ulid import new_ulid

if TYPE_CHECKING:
    from octop.infra.agents.manager import AgentManager
    from octop.infra.db.repos.sessions import SessionRow
    from octop.infra.db.repos.thread_messages import ThreadMessageInput
    from octop.infra.db.services import RepoBundle
    from octop.infra.gateway.gateway import Gateway

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CronDeliveryCommand:
    """Immutable inputs for one scheduled delivery attempt."""

    cron_id: str
    cron_name: str
    agent_id: str
    user_id: int
    session_key: str
    prompt: str
    fresh_thread: bool
    task_type: CronTaskType
    model: str | None
    mcp_servers: tuple[str, ...]
    allow_all: bool = False
    script_lang: str | None = None
    script_source: str | None = None
    script_path: str | None = None


class CronDeliveryService:
    """Persist canonical cron turns and deliver their visible output."""

    def __init__(
        self,
        *,
        gateway: Gateway,
        agent_manager: AgentManager,
        repos: RepoBundle,
    ) -> None:
        self._gateway = gateway
        self._agent_manager = agent_manager
        self._repos = repos

    def replace_repos(self, repos: RepoBundle) -> None:
        """Retarget projection and locale lookups after a control-plane swap."""
        self._repos = repos

    async def deliver(self, command: CronDeliveryCommand) -> None:
        """Run one delivery under the target channel session lock."""
        session_key, pinned = self._target_session(command)
        registry = self._gateway.thread_registry
        recovered_thread_id = None
        if registry.get_session(session_key) is None:
            if session_key != ThreadRegistry.dashboard_key(
                agent_id=command.agent_id, user_id=command.user_id
            ):
                raise self._missing_target_error(command.user_id)
            # Gateway.run_in_session requires the session to resolve its channel.
            recovered_thread_id = await registry.get_or_create_by_key(
                session_key=session_key,
                agent_id=command.agent_id,
                user_id=command.user_id,
                channel_type=ThreadRegistry.CHANNEL_DASHBOARD,
            )

        async def _locked() -> None:
            session = self._gateway.require_session(command.agent_id, session_key)
            if session.user_id != command.user_id:
                raise ValueError(
                    f"session {command.session_key!r} does not belong to user {command.user_id!r}"
                )
            if command.fresh_thread:
                # Reuse the recovery thread if it is still empty when we acquire the lock.
                recovered = (
                    registry.get_thread(session.thread_id)
                    if session.thread_id == recovered_thread_id
                    else None
                )
                if recovered is None or recovered.last_active > 0:
                    await registry.reset_by_session_key(session_key)
            elif pinned:
                await self._bind_pinned_thread(session_key, pinned)
            else:
                await self._bind_latest_thread(session_key)
            session = self._gateway.require_session(command.agent_id, session_key)
            if command.task_type == "text":
                await self._publish_fixed(command, session, command.prompt)
            elif command.task_type == "script":
                await self._deliver_script(command, session)
            else:
                await self._deliver_agent(command, session)

        await self._gateway.run_in_session(
            command.agent_id,
            session_key,
            _locked,
        )

    async def _publish_fixed(
        self,
        command: CronDeliveryCommand,
        session: SessionRow,
        outbound: str,
    ) -> None:
        projected: list[ThreadMessageInput] = []
        title_source = outbound
        if session.channel_type == ThreadRegistry.CHANNEL_DASHBOARD:
            delivery_id = new_ulid()
            locale = resolve_user_locale(
                user_repo=self._repos.user_repo,
                user_id=session.user_id,
                channel_type=session.channel_type,
            )
            human_text = tr(
                "cron.history.executed",
                locale,
                cron_id=command.cron_id,
                name=command.cron_name,
            )
            title_source = human_text
            canonical = [
                HumanMessage(
                    content=human_text,
                    id=f"cron:{delivery_id}:human",
                ),
                AIMessage(
                    content=outbound,
                    id=f"cron:{delivery_id}:assistant",
                ),
            ]
            harness = self._agent_manager.get_agent(command.agent_id)
            appended = await harness.aappend_messages(session.thread_id, canonical)
            projected = message_inputs(appended, dedupe_missing_ids=True)

        self._project_best_effort(session.thread_id, projected)
        self._remember_thread_title(session, command)
        await self._gateway.push_session_text(
            session,
            outbound,
            title_source=title_source,
        )
        await self._notify_best_effort(session, command.agent_id, outbound)

    async def _deliver_script(
        self,
        command: CronDeliveryCommand,
        session: SessionRow,
    ) -> None:
        locale = resolve_user_locale(
            user_repo=self._repos.user_repo,
            user_id=session.user_id,
            channel_type=session.channel_type,
        )
        workspace = self._agent_manager.workspace_for_agent(command.agent_id)
        if workspace is None:
            raise RuntimeError(tr("cron.script.unreadable", locale, path=command.script_path or ""))
        try:
            result = await run_cron_script(
                lang=command.script_lang or "",
                source=command.script_source or "inline",
                body=command.prompt,
                path=command.script_path,
                workspace=workspace,
                backend_spec=self._backend_spec(command.agent_id),
            )
        except ScriptRunError as exc:
            raise RuntimeError(self._script_error_text(exc, locale, command)) from exc
        if result.exit_code != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(
                tr(
                    "cron.script.failed",
                    locale,
                    code=result.exit_code,
                    detail=detail[:2000],
                )
            )
        outbound = result.stdout.strip() or tr(
            "cron.history.script_done",
            locale,
            name=command.cron_name,
        )
        await self._publish_fixed(command, session, outbound)

    def _backend_spec(self, agent_id: str) -> Any:
        row = self._agent_manager.get_row(agent_id)
        method = getattr(self._agent_manager, "_backend_spec_for_row", None)
        if row is None or not callable(method):
            return None
        try:
            return method(row)
        except Exception:
            logger.warning(
                "cron script could not read backend spec for %s", agent_id, exc_info=True
            )
            return None

    def _script_error_text(
        self,
        exc: ScriptRunError,
        locale: str,
        command: CronDeliveryCommand,
    ) -> str:
        runtime = command.script_lang or exc.detail or ""
        if exc.code == "interpreter_missing":
            return tr("cron.script.interpreter_missing", locale, runtime=runtime)
        if exc.code == "timeout":
            return tr("cron.script.timeout", locale, seconds=exc.detail or "120")
        return tr("cron.script.unreadable", locale, path=exc.detail or command.script_path or "")

    async def _deliver_agent(
        self,
        command: CronDeliveryCommand,
        session: SessionRow,
    ) -> None:
        request = await self._build_agent_request(command, session)
        if command.allow_all:
            _stamp_managed_allow_all(self._agent_manager, command.agent_id, request)
        tracker = TurnHistoryTracker.from_request(request)
        meter = TurnMeter(command.agent_id, source="cron")
        usage = UsageTracker(request_model=str(request.get("model") or ""), meter=meter)
        parts: list[str] = []
        interaction_required = False
        saw_tool_call = False
        emitted_tool_error_ids: set[str] = set()
        meter.start()
        try:
            from octop.infra.connectors.gateway.adapters.agently_cli import write_scope

            store = getattr(self._agent_manager, "_hitl_session_store", None)
            policy = ephemeral_hitl_policy(
                store if command.allow_all else None,
                session.thread_id,
                HitlSessionPolicy(mode="allow_all"),
            )
            with write_scope(allowed=False), policy:
                async for chunk in self._agent_manager.stream(command.agent_id, request):
                    tracker.observe(chunk)
                    usage.observe(chunk)
                    kind = chunk.get("type")
                    if kind == "tool_call_chunk":
                        saw_tool_call = True
                    elif kind == "tool_result":
                        log_failed_tool_results(
                            chunk,
                            agent_id=command.agent_id,
                            thread_id=session.thread_id,
                            seen=emitted_tool_error_ids,
                            live=saw_tool_call,
                        )
                    if kind in ("token", "delta"):
                        parts.append(str(chunk.get("content") or chunk.get("text") or ""))
                    elif kind == "hitl_required":
                        interaction_required = True
            if interaction_required:
                raise RuntimeError("cron agent run requires user interaction")
            outbound = strip_thinking("".join(parts)).strip()
            if not outbound:
                raise RuntimeError("cron agent run produced no visible response")
            meter.finish()
        except Exception as exc:
            meter.finish(exc)
            raise
        finally:
            meter.finish(record_duration=False)
            # ``fresh_thread`` already put an empty thread on the session, so a run
            # that raised before this left a conversation with no rows at all.
            self._project_best_effort(session.thread_id, tracker.inputs)
            self._remember_thread_title(session, command)
        if usage.usage is not None:
            record_turn_usage(
                self._repos.usage_repo,
                agent_id=command.agent_id,
                user_id=session.user_id,
                thread_id=session.thread_id,
                usage=usage.usage,
                source="cron",
            )
        await self._gateway.push_session_text(
            session,
            outbound,
            title_source=command.prompt,
        )
        await self._notify_best_effort(session, command.agent_id, outbound)

    async def _build_agent_request(
        self,
        command: CronDeliveryCommand,
        session: SessionRow,
    ) -> dict[str, Any]:
        picked = [name.strip() for name in command.mcp_servers if name.strip()]
        resolved = await resolve_turn_mcp(
            self._agent_manager,
            agent_id=command.agent_id,
            user_id=session.user_id,
            explicit=picked or None,
            apply_defaults=not picked,
        )
        if resolved is not None and resolved.failed:
            raise RuntimeError(f"mcp load failed: {', '.join(resolved.failed)}")
        servers = resolved.harness if resolved is not None else []
        shown_servers = resolved.shown if resolved is not None else []

        row = self._agent_manager.get_row(command.agent_id)
        default_model = (row.default_model if row is not None else None) or None
        composer = build_composer_context(
            mcp_servers=shown_servers or None,
            skills=None,
            target_agent_ids=None,
            model_ref=command.model,
            default_model=default_model,
        )
        message_kwargs = {COMPOSER_CTX_KEY: composer} if composer else None
        request = build_harness_request(
            thread_id=session.thread_id,
            user_id=session.user_id,
            agent_id=command.agent_id,
            session_key=command.session_key,
            source=session.channel_type,
            text=command.prompt,
            model=command.model,
            message_kwargs=message_kwargs,
        )
        if servers:
            request["mcp_servers"] = servers
        self._attach_turn_knowledge_config(request, command, session)
        return request

    def _attach_turn_knowledge_config(
        self,
        request: dict[str, Any],
        command: CronDeliveryCommand,
        session: SessionRow,
    ) -> None:
        user_row = self._repos.user_repo.get(session.user_id)
        is_admin = str(getattr(user_row, "role", "") or "") == "admin"
        locale = resolve_user_locale(
            user_repo=self._repos.user_repo,
            user_id=session.user_id,
            channel_type=session.channel_type,
        )
        attach_turn_knowledge(
            request,
            knowledge_repo=self._repos.knowledge_repo,
            user_id=session.user_id,
            is_admin=is_admin,
            explicit_ids=None,
            extra_ids=self._agent_manager.default_knowledge_base_ids(command.agent_id),
            locale=locale,
        )

    def _target_session(self, command: CronDeliveryCommand) -> tuple[str, str | None]:
        """Return the channel session and, for a history pick, its thread id."""
        pinned = pinned_thread_id(command.session_key)
        if not pinned:
            return command.session_key, None
        row = self._gateway.thread_registry.get_thread(pinned)
        if (
            not isinstance(row, ThreadRow)
            or row.agent_id != command.agent_id
            or row.user_id != command.user_id
        ):
            raise self._missing_target_error(command.user_id)
        return row.session_key, pinned

    def _missing_target_error(self, user_id: int) -> ValueError:
        locale = resolve_user_locale(user_repo=self._repos.user_repo, user_id=user_id)
        return ValueError(tr("cron.missing_target_session", locale))

    async def _bind_pinned_thread(self, session_key: str, thread_id: str) -> None:
        """Point the channel at the historical conversation chosen for this job."""
        registry = self._gateway.thread_registry
        if registry.get_bound_thread_id(session_key) == thread_id:
            return
        session = registry.get_session(session_key)
        if session is None:
            return
        await registry.rebind(
            session_key=session_key,
            thread_id=thread_id,
            agent_id=session.agent_id,
            acting_user_id=session.user_id,
        )

    async def _bind_latest_thread(self, session_key: str) -> None:
        """Point this channel at its latest conversation before the run.

        The stored ``session_key`` names the channel. Several threads can share
        it; delivery follows the one the user last spoke in, not whichever
        thread happens to be open.
        """
        registry = self._gateway.thread_registry
        latest = registry.latest_active_thread(session_key=session_key)
        if not isinstance(latest, ThreadRow):
            return
        if registry.get_bound_thread_id(session_key) == latest.thread_id:
            return
        session = registry.get_session(session_key)
        if session is None:
            return
        await registry.rebind(
            session_key=session_key,
            thread_id=latest.thread_id,
            agent_id=session.agent_id,
            acting_user_id=session.user_id,
        )

    def _remember_thread_title(self, session: SessionRow, command: CronDeliveryCommand) -> None:
        """Name the conversation when the scheduled run writes it.

        Push only titles dashboard/CLI sessions, and only after the channel
        accepts the text. A failed push, an IM target, or an agent run that
        died after projecting history left ``threads.title`` null until the
        user sent the next message.
        """
        title = (command.cron_name or "").strip() or (command.prompt or "").strip()
        if not title:
            return
        try:
            self._gateway.thread_registry.set_title_if_null(session.thread_id, title)
        except Exception:
            logger.warning(
                "failed to title cron thread=%s",
                session.thread_id,
                exc_info=True,
            )

    def _project_best_effort(
        self,
        thread_id: str,
        messages: list[ThreadMessageInput],
    ) -> None:
        if not messages:
            return
        try:
            self._repos.thread_message_repo.append_if_ready(thread_id, messages)
        except Exception:
            logger.warning(
                "failed to append cron history projection for thread=%s",
                thread_id,
                exc_info=True,
            )

    async def _notify_best_effort(
        self,
        session: SessionRow,
        agent_id: str,
        text: str,
    ) -> None:
        if session.channel_type != ThreadRegistry.CHANNEL_DASHBOARD:
            return
        try:
            await self._gateway.notify_dashboard_push(session, agent_id, text)
        except Exception:
            logger.warning(
                "failed to send cron dashboard notification for thread=%s",
                session.thread_id,
                exc_info=True,
            )


def _stamp_managed_allow_all(manager: Any, agent_id: str, request: dict[str, Any]) -> None:
    """Turn this run into the managed expert's unattended mode without saving it."""
    from octop.infra.agents.acp.session_modes import yolo_session_mode_id
    from octop.infra.agents.managed import is_managed_agent

    row = manager.get_row(agent_id)
    if row is None or not is_managed_agent(row):
        return
    config: dict[str, Any] = {}
    getter = getattr(manager, "get_config", None)
    if callable(getter):
        try:
            loaded = getter(agent_id)
        except Exception:
            logger.warning("cron allow-all could not read config for %s", agent_id, exc_info=True)
            loaded = None
        if isinstance(loaded, dict):
            config = loaded
    runner = config.get("managed_runner")
    mode = yolo_session_mode_id(runner if isinstance(runner, str) else "")
    configurable = request.get("configurable")
    if not isinstance(configurable, dict):
        configurable = {}
        request["configurable"] = configurable
    if mode:
        request["session_mode"] = mode
        configurable["acp_session_mode"] = mode
    configurable["acp_permission_mode"] = "yolo"


def command_from_row(row: Any) -> CronDeliveryCommand:
    """Build a delivery command from a persisted cron row."""
    return CronDeliveryCommand(
        cron_id=str(row.cron_id),
        cron_name=str(row.name),
        agent_id=str(row.agent_id),
        user_id=int(row.user_id),
        session_key=str(row.session_key),
        prompt=str(row.prompt),
        fresh_thread=bool(row.fresh_thread),
        task_type=normalize_cron_task_type(str(row.task_type)),
        model=str(row.model) if row.model else None,
        mcp_servers=tuple(str(name) for name in row.mcp_servers),
        allow_all=bool(getattr(row, "allow_all", False)),
        script_lang=getattr(row, "script_lang", None),
        script_source=getattr(row, "script_source", None),
        script_path=getattr(row, "script_path", None),
    )


__all__ = [
    "CronDeliveryCommand",
    "CronDeliveryService",
    "command_from_row",
]
