"""Cron delivery orchestration, separate from channel transport.

The agent-turn path is **shared**, not cron-specific: :func:`build_agent_turn_request`
assembles the harness request (thread, ``session_key``, MCP, team-host branch) and
:func:`run_agent_turn` runs one turn, projects its history, and records usage.
Cron calls both from :meth:`CronDeliveryService._deliver_agent`; project task
dispatch (plan §T2.5) calls the same functions with a custom prompt instead of
growing a second copy of the path.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, HumanMessage

from octop.i18n import tr
from octop.infra.cron.task_type import CronTaskType, normalize_cron_task_type
from octop.infra.gateway.process import build_harness_request
from octop.infra.gateway.process.message_keys import COMPOSER_CTX_KEY, build_composer_context
from octop.infra.gateway.process.usage_record import UsageTracker, record_turn_usage
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.history.projection import TurnHistoryTracker, message_inputs
from octop.infra.knowledge.default_open import stamp_turn_knowledge_config
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

        _project_best_effort(self._repos, session.thread_id, projected)
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
        outbound = await run_agent_turn(
            agent_manager=self._agent_manager,
            repos=self._repos,
            agent_id=command.agent_id,
            session=session,
            prompt=command.prompt,
            model=command.model,
            mcp_servers=command.mcp_servers,
        )
        await self._gateway.push_session_text(
            session,
            outbound,
            title_source=command.prompt,
        )
        await self._notify_best_effort(session, command.agent_id, outbound)

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


async def build_agent_turn_request(
    *,
    agent_manager: AgentManager,
    repos: RepoBundle,
    agent_id: str,
    session: SessionRow,
    prompt: str,
    model: str | None = None,
    mcp_servers: Sequence[str] = (),
) -> dict[str, Any]:
    """Assemble one harness request for a turn delivered outside an inbound message.

    Takes the prompt as a parameter so callers other than cron can supply their own
    text — project task dispatch (plan §T2.5) reuses this instead of re-implementing
    thread / ``session_key`` / MCP / team-host assembly.

    ``session.session_key`` is used as the request's session key: callers reach the
    session through it (``Gateway.require_session``), so the two cannot diverge.
    """
    from octop.infra.agents.teams import is_team_agent

    if is_team_agent(agent_manager.get_row(agent_id)):
        servers: list[str] = []
    else:
        servers = [name.strip() for name in mcp_servers if name.strip()]
        extra_defaults = agent_manager.default_mcp_servers(agent_id)
        if servers:
            servers = (
                agent_manager.merge_turn_mcp_servers(
                    session.user_id,
                    servers,
                    apply_defaults=False,
                    extra_defaults=extra_defaults,
                )
                or []
            )
        else:
            servers = (
                agent_manager.merge_turn_mcp_servers(
                    session.user_id,
                    None,
                    apply_defaults=True,
                    extra_defaults=extra_defaults,
                )
                or []
            )
    if servers:
        failed = await agent_manager.prepare_chat_mcp(
            agent_id,
            servers,
            connector_user_id=session.user_id,
        )
        if failed:
            raise RuntimeError(f"mcp load failed: {', '.join(failed)}")

    row = agent_manager.get_row(agent_id)
    default_model = (row.default_model if row is not None else None) or None
    composer = build_composer_context(
        mcp_servers=servers or None,
        skills=None,
        target_agent_ids=None,
        model_ref=model,
        default_model=default_model,
    )
    message_kwargs = {COMPOSER_CTX_KEY: composer} if composer else None
    request = build_harness_request(
        thread_id=session.thread_id,
        user_id=session.user_id,
        agent_id=agent_id,
        session_key=session.session_key,
        source=session.channel_type,
        text=prompt,
        model=model,
        message_kwargs=message_kwargs,
    )
    if servers:
        request["mcp_servers"] = servers
    _attach_turn_knowledge_config(
        request,
        agent_manager=agent_manager,
        repos=repos,
        agent_id=agent_id,
        session=session,
    )
    return request


async def run_agent_turn(
    *,
    agent_manager: AgentManager,
    repos: RepoBundle,
    agent_id: str,
    session: SessionRow,
    prompt: str,
    model: str | None = None,
    mcp_servers: Sequence[str] = (),
    usage_source: str = "cron",
    turn_label: str = "cron",
    prepare_request: Callable[[dict[str, Any]], None] | None = None,
) -> str:
    """Run one agent turn on *session* and return its visible text.

    Extracted from ``CronDeliveryService._deliver_agent`` (plan §T2.5: extract the
    path rather than duplicating it). Behaviour is unchanged for cron:

    - ``prepare_request`` runs after the request is assembled and before the stream;
      project dispatch stamps the team-host runtime there.
    - A run that needs user interaction, or produces no visible text, raises.
    - ``tracker.inputs`` is projected even when the run fails, so a dead turn never
      leaves an empty conversation.
    """
    request = await build_agent_turn_request(
        agent_manager=agent_manager,
        repos=repos,
        agent_id=agent_id,
        session=session,
        prompt=prompt,
        model=model,
        mcp_servers=mcp_servers,
    )
    if prepare_request is not None:
        prepare_request(request)
    tracker = TurnHistoryTracker.from_request(request)
    usage = UsageTracker()
    parts: list[str] = []
    interaction_required = False
    try:
        async for chunk in agent_manager.stream(agent_id, request):
            tracker.observe(chunk)
            usage.observe(chunk)
            if chunk.get("type") in ("token", "delta"):
                parts.append(str(chunk.get("content") or chunk.get("text") or ""))
            elif chunk.get("type") == "hitl_required":
                interaction_required = True
        if interaction_required:
            raise RuntimeError(f"{turn_label} agent run requires user interaction")
        outbound = strip_thinking("".join(parts)).strip()
        if not outbound:
            raise RuntimeError(f"{turn_label} agent run produced no visible response")
    finally:
        # ``fresh_thread`` already put an empty thread on the session, so a run
        # that raised before this left a conversation with no rows at all.
        _project_best_effort(repos, session.thread_id, tracker.inputs)
    if usage.usage is not None:
        record_turn_usage(
            repos.usage_repo,
            agent_id=agent_id,
            user_id=session.user_id,
            thread_id=session.thread_id,
            usage=usage.usage,
            source=usage_source,
        )
    return outbound


def _attach_turn_knowledge_config(
    request: dict[str, Any],
    *,
    agent_manager: AgentManager,
    repos: RepoBundle,
    agent_id: str,
    session: SessionRow,
) -> None:
    user_row = repos.user_repo.get(session.user_id)
    is_admin = str(getattr(user_row, "role", "") or "") == "admin"
    knowledge_repo = repos.knowledge_repo
    bases = knowledge_repo.list_all() if is_admin else knowledge_repo.list_visible(session.user_id)
    locale = resolve_user_locale(
        user_repo=repos.user_repo,
        user_id=session.user_id,
        channel_type=session.channel_type,
    )
    stamp_turn_knowledge_config(
        request,
        visible_bases=bases,
        explicit_ids=None,
        owner_user_id=session.user_id,
        extra_ids=agent_manager.default_knowledge_base_ids(agent_id),
        is_admin=is_admin,
        locale=locale,
    )


def _project_best_effort(
    repos: RepoBundle,
    thread_id: str,
    messages: list[ThreadMessageInput],
) -> None:
    if not messages:
        return
    try:
        repos.thread_message_repo.append_if_ready(thread_id, messages)
    except Exception:
        logger.warning(
            "failed to append cron history projection for thread=%s",
            thread_id,
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
    "build_agent_turn_request",
    "command_from_row",
    "run_agent_turn",
]
