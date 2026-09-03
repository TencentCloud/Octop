"""Cron delivery orchestration, separate from channel transport."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, HumanMessage

from octop.i18n import tr
from octop.infra.cron.task_type import CronTaskType, normalize_cron_task_type
from octop.infra.gateway.process import build_harness_request
from octop.infra.gateway.process.history_projection import TurnHistoryTracker, message_inputs
from octop.infra.gateway.process.message_keys import COMPOSER_CTX_KEY, build_composer_context
from octop.infra.gateway.process.usage_record import UsageTracker, record_turn_usage
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.llm_text import strip_thinking
from octop.infra.utils.locale import resolve_user_locale
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

        async def _locked() -> None:
            if command.fresh_thread:
                await self._gateway.thread_registry.reset_by_session_key(command.session_key)
            session = self._gateway.require_session(command.agent_id, command.session_key)
            if session.user_id != command.user_id:
                raise ValueError(
                    f"session {command.session_key!r} does not belong to user {command.user_id!r}"
                )
            if command.task_type == "text":
                await self._deliver_text(command, session)
            else:
                await self._deliver_agent(command, session)

        await self._gateway.run_in_session(
            command.agent_id,
            command.session_key,
            _locked,
        )

    async def _deliver_text(
        self,
        command: CronDeliveryCommand,
        session: SessionRow,
    ) -> None:
        projected: list[ThreadMessageInput] = []
        title_source = command.prompt
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
                    content=command.prompt,
                    id=f"cron:{delivery_id}:assistant",
                ),
            ]
            harness = self._agent_manager.get_agent(command.agent_id)
            appended = await harness.aappend_messages(session.thread_id, canonical)
            projected = message_inputs(appended, dedupe_missing_ids=True)

        self._project_best_effort(session.thread_id, projected)
        await self._gateway.push_session_text(
            session,
            command.prompt,
            title_source=title_source,
        )
        await self._notify_best_effort(session, command.agent_id, command.prompt)

    async def _deliver_agent(
        self,
        command: CronDeliveryCommand,
        session: SessionRow,
    ) -> None:
        request = await self._build_agent_request(command, session)
        tracker = TurnHistoryTracker.from_request(request)
        usage = UsageTracker()
        parts: list[str] = []
        interaction_required = False
        async for chunk in self._agent_manager.stream(command.agent_id, request):
            tracker.observe(chunk)
            usage.observe(chunk)
            if chunk.get("type") in ("token", "delta"):
                parts.append(str(chunk.get("content") or chunk.get("text") or ""))
            elif chunk.get("type") == "hitl_required":
                interaction_required = True
        if interaction_required:
            raise RuntimeError("cron agent run requires user interaction")

        outbound = strip_thinking("".join(parts)).strip()
        if not outbound:
            raise RuntimeError("cron agent run produced no visible response")
        self._project_best_effort(session.thread_id, tracker.inputs)
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
        servers = [name.strip() for name in command.mcp_servers if name.strip()]
        if servers:
            servers = (
                self._agent_manager.merge_turn_mcp_servers(
                    session.user_id,
                    servers,
                    apply_defaults=False,
                )
                or []
            )
        else:
            servers = (
                self._agent_manager.merge_turn_mcp_servers(
                    session.user_id,
                    None,
                    apply_defaults=True,
                )
                or []
            )
        if servers:
            failed = await self._agent_manager.prepare_chat_mcp(
                command.agent_id,
                servers,
                connector_user_id=session.user_id,
            )
            if failed:
                raise RuntimeError(f"mcp load failed: {', '.join(failed)}")

        row = self._agent_manager.get_row(command.agent_id)
        default_model = (row.default_model if row is not None else None) or None
        composer = build_composer_context(
            mcp_servers=servers or None,
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
        return request

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
    )


__all__ = [
    "CronDeliveryCommand",
    "CronDeliveryService",
    "command_from_row",
]
