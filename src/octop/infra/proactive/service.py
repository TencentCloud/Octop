"""ProactiveCareService — proactive care push service.

Procedural flow (bypasses the LangGraph ReAct loop):
1. Read the last N days of episodes from Memory.
2. Query push records and filter out already-pushed episodes.
3. Use EpisodePicker to select the Top-3 most care-worthy episodes.
4. Read the agent's SOUL.md and embed it into the LLM system prompt.
5. Call a lightweight LLM to generate a care message (<=200 chars).
6. Under the session lock, bind the latest active thread, append a single
   AIMessage to the harness checkpoint and thread_messages projection, push
   over the session transport, and (for dashboard) send the toast notification.
7. Write push + reply-tracking records to care_push_records after delivery.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from octop.i18n.loader import tr as i18n_tr
from octop.infra.db.repos.threads import ThreadRow
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.history.projection import message_inputs
from octop.infra.proactive.picker import EpisodePicker
from octop.infra.utils.llm_text import ainvoke_text
from octop.infra.utils.locale import normalize_locale
from octop.infra.utils.ulid import new_ulid

if TYPE_CHECKING:
    from octop.infra.agents.manager import AgentManager
    from octop.infra.db.repos.care_push import CarePushRepo
    from octop.infra.db.repos.sessions import SessionRow
    from octop.infra.db.repos.thread_messages import ThreadMessageRepo
    from octop.infra.gateway.gateway import Gateway

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_CARE_TEXT_LEN = 200  # max length of a care message (chars)
_DEFAULT_WINDOW_DAYS = 7  # default time window (days)
_FALLBACK_WINDOW_DAYS = 30  # fallback time window (days)


def _today_in_timezone(now: datetime, timezone_name: str, *, locale: str) -> str:
    """Format *now* as a calendar date in the configured server timezone."""
    try:
        local = now.astimezone(ZoneInfo(timezone_name))
    except Exception:
        local = now.astimezone()
    if locale == "zh":
        return local.strftime("%Y-%m-%d")
    return local.strftime("%B %d, %Y")


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def _format_episodes_for_prompt(episodes: list[Any]) -> str:
    """Format the episode list into LLM prompt context.

    Uses plain English field names — this is structured data for the LLM,
    not user-facing text, so locale does not matter here.
    """
    lines: list[str] = []
    for i, ep in enumerate(episodes, 1):
        occurred = ep.occurred_at.strftime("%Y-%m-%d") if ep.occurred_at else "unknown date"
        people_str = ", ".join(ep.people) if ep.people else ""
        people_note = f" (involves: {people_str})" if people_str else ""
        lines.append(
            f"{i}. [{occurred}] {ep.summary}{people_note}\n"
            f"   Quote: {ep.verbatim_quote}\n"
            f"   Emotion: {ep.emotion} (intensity {ep.intensity}/5)"
        )
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# ProactiveCareService
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _DeliveredCare:
    """Delivery coordinates recorded after persisting and pushing a care message."""

    thread_id: str
    message_id: str


class ProactiveCareService:
    """Proactive care push service.

    A procedural flow driven directly by the scheduler, not going through the
    LangGraph agent's ReAct loop.

    Args:
        gateway: Gateway instance used to push messages.
        care_push_repo: CarePushRepo instance used for dedup and reply tracking.
        agent_manager: AgentManager instance used to obtain HarnessAgent and Memory.
        thread_message_repo: Optional ThreadMessageRepo for dashboard history projection.
    """

    def __init__(
        self,
        *,
        gateway: Gateway,
        care_push_repo: CarePushRepo,
        agent_manager: AgentManager,
        thread_message_repo: ThreadMessageRepo | None = None,
        timezone: str = "Asia/Shanghai",
    ) -> None:
        self._gateway = gateway
        self._care_push_repo = care_push_repo
        self._agent_manager = agent_manager
        self._thread_message_repo = thread_message_repo
        self._timezone = timezone or "Asia/Shanghai"
        self._picker = EpisodePicker(
            top_k=3,
            window_days=_DEFAULT_WINDOW_DAYS,
            fallback_days=_FALLBACK_WINDOW_DAYS,
        )

    def replace_care_push_repo(
        self,
        care_push_repo: CarePushRepo,
        thread_message_repo: ThreadMessageRepo | None = None,
    ) -> None:
        """Point dedup and history projection storage at a rebound control-plane pool."""
        self._care_push_repo = care_push_repo
        if thread_message_repo is not None:
            self._thread_message_repo = thread_message_repo

    async def _bind_latest_thread(self, session_key: str) -> None:
        """Point *session_key* at its latest active conversation, skipping blank threads."""
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

    def _project_best_effort(self, thread_id: str, appended: list[Any]) -> None:
        if self._thread_message_repo is None or not appended:
            return
        try:
            self._thread_message_repo.append_if_ready(
                thread_id,
                message_inputs(appended, dedupe_missing_ids=True),
            )
        except Exception:
            logger.warning(
                "ProactiveCareService: failed to append history projection thread=%s",
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
                "ProactiveCareService: failed to send dashboard notification thread=%s",
                session.thread_id,
                exc_info=True,
            )

    async def _deliver(
        self,
        agent_id: str,
        session_key: str,
        care_text: str,
        *,
        can_send: Callable[[], bool] | None = None,
    ) -> _DeliveredCare | None:
        """Persist a single AIMessage to checkpoint + projection, then push it.

        ``Gateway.push_text_from_session`` is transport-only; persisting here
        keeps dashboard history, unread badges, and next-turn agent context in
        sync across both dashboard and IM sessions.
        """
        delivered: _DeliveredCare | None = None

        async def _locked() -> None:
            nonlocal delivered
            if can_send is not None and not can_send():
                logger.info(
                    "ProactiveCareService: user activity changed before locked delivery, "
                    "discarding agent=%s",
                    agent_id,
                )
                return
            await self._bind_latest_thread(session_key)
            session = self._gateway.require_session(agent_id, session_key)
            message_id = f"care:{new_ulid()}:assistant"
            harness = self._agent_manager.get_agent(agent_id)
            appended = await harness.aappend_messages(
                session.thread_id,
                [AIMessage(content=care_text, id=message_id)],
            )
            self._project_best_effort(session.thread_id, appended)
            await self._gateway.push_session_text(
                session,
                care_text,
                title_source=care_text,
            )
            await self._notify_best_effort(session, agent_id, care_text)
            delivered = _DeliveredCare(thread_id=session.thread_id, message_id=message_id)

        await self._gateway.run_in_session(agent_id, session_key, _locked)
        return delivered

    async def run(
        self,
        agent_id: str,
        session_key: str,
        *,
        can_send: Callable[[], bool] | None = None,
    ) -> None:
        """Run one proactive care push.

        Args:
            agent_id: The agent ID to push for.
            session_key: The session key to push to.
            can_send: Rechecked after the message is written and before it is
                delivered. A false result drops the message, matching finnie's
                discard when the user starts a turn during generation.
        """
        logger.info(
            "ProactiveCareService: starting push agent=%s session=%s", agent_id, session_key
        )

        # 1. Get the Memory instance
        try:
            agent = self._agent_manager.get_agent(agent_id)
            memory = agent.memory
            if memory is None:
                logger.info(
                    "ProactiveCareService: memory not enabled, skipping push agent=%s", agent_id
                )
                return
        except Exception as exc:
            logger.warning(
                "ProactiveCareService: failed to get agent memory agent=%s: %s", agent_id, exc
            )
            return

        # 2. Read all episodes from the last fallback_days days (picker filters by window internally)
        now = datetime.now(UTC)
        after = now - timedelta(days=_FALLBACK_WINDOW_DAYS)
        try:
            episodes = memory.list_episodes(after=after, limit=200)
        except Exception as exc:
            logger.warning("ProactiveCareService: list_episodes failed agent=%s: %s", agent_id, exc)
            return

        logger.info(
            "ProactiveCareService: read %d episodes agent=%s",
            len(episodes),
            agent_id,
        )
        if not episodes:
            logger.info(
                "ProactiveCareService: no recent episodes, skipping push agent=%s", agent_id
            )
            return

        # 3. Query pushed records
        try:
            pushed_ids = self._care_push_repo.list_pushed_episode_ids(
                agent_id, after_days=_FALLBACK_WINDOW_DAYS
            )
        except Exception as exc:
            logger.warning(
                "ProactiveCareService: failed to query push records agent=%s: %s", agent_id, exc
            )
            pushed_ids = set()

        logger.info(
            "ProactiveCareService: found %d existing push records agent=%s",
            len(pushed_ids),
            agent_id,
        )

        # 4. Pick the Top-K episodes
        pick_result = self._picker.pick(episodes, pushed_ids=pushed_ids, now=now)
        if not pick_result.episodes:
            logger.info(
                "ProactiveCareService: no new episodes to push, skipping agent=%s", agent_id
            )
            return
        logger.info(
            "ProactiveCareService: picker selected %d episodes (window_days=%d) agent=%s",
            len(pick_result.episodes),
            pick_result.window_days,
            agent_id,
        )

        # 5. Read SOUL.md and embed it into the system prompt
        soul_md = ""
        try:
            ws = agent.workspace
            soul_md = await ws.aread_text("SOUL.md") or ""
        except Exception as exc:
            logger.debug(
                "ProactiveCareService: failed to read SOUL.md agent=%s: %s (falling back to default prompt)",
                agent_id,
                exc,
            )

        # Resolve locale from agent config (locale or language); default to zh.
        agent_config = getattr(agent, "config", None)
        raw_locale = (
            getattr(agent_config, "locale", None) or getattr(agent_config, "language", None)
            if agent_config is not None
            else None
        )
        locale = normalize_locale(str(raw_locale) if raw_locale is not None else None)

        # Build the system prompt from i18n JSON.
        today_str = _today_in_timezone(now, self._timezone, locale=locale)
        soul_md_stripped = soul_md.strip()
        if soul_md_stripped:
            system_prompt = i18n_tr(
                "proactive_care.system_prompt_with_soul",
                locale,
                today=today_str,
                soul_md=soul_md_stripped,
            )
        else:
            system_prompt = i18n_tr(
                "proactive_care.system_prompt",
                locale,
                today=today_str,
            )

        # 6. Call the LLM to generate the care message
        episode_context = _format_episodes_for_prompt(pick_result.episodes)
        try:
            llm = agent.model_factory.get(agent.config.pick_default_model_ref())
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"User's recent life events:\n\n{episode_context}"),
            ]
            care_text = await ainvoke_text(llm, messages, timeout=30.0)
            # Truncate to the max length
            if len(care_text) > _MAX_CARE_TEXT_LEN:
                care_text = care_text[:_MAX_CARE_TEXT_LEN]
            logger.info(
                "ProactiveCareService: LLM generated care message (%d chars) agent=%s: %s",
                len(care_text),
                agent_id,
                care_text[:50] + "..." if len(care_text) > 50 else care_text,
            )
        except Exception as exc:
            logger.warning("ProactiveCareService: LLM call failed agent=%s: %s", agent_id, exc)
            return  # do not push, do not write a record

        # 7. Persist and push the message directly without invoking the agent.
        if can_send is not None and not can_send():
            logger.info(
                "ProactiveCareService: user activity changed during generation, discarding agent=%s",
                agent_id,
            )
            return
        try:
            delivered = await self._deliver(
                agent_id,
                session_key,
                care_text,
                can_send=can_send,
            )
        except Exception as exc:
            logger.warning(
                "ProactiveCareService: push failed agent=%s session=%s: %s",
                agent_id,
                session_key,
                exc,
            )
            return  # do not write a record

        if delivered is None:
            return

        # 8. Write dedup + reply-tracking records (only after a successful push)
        episode_ids = [ep.id for ep in pick_result.episodes]
        try:
            self._care_push_repo.insert(
                agent_id=agent_id,
                session_key=session_key,
                episode_ids=episode_ids,
                thread_id=delivered.thread_id,
                message_id=delivered.message_id,
                care_text=care_text,
            )
        except Exception as exc:
            # A failed write does not affect the push result; just log it
            logger.warning(
                "ProactiveCareService: failed to write push record agent=%s: %s", agent_id, exc
            )

        logger.info(
            "ProactiveCareService: push succeeded agent=%s session=%s thread=%s episodes=%d window_days=%d",
            agent_id,
            session_key,
            delivered.thread_id,
            len(episode_ids),
            pick_result.window_days,
        )
