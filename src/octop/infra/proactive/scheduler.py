"""ProactiveCareScheduler — proactive care push random scheduler.

Core idea: after each push completes, immediately schedule the next push time at
random. Push times are randomly distributed within the user-configured active
hours, rather than triggered at a fixed moment.

Random scheduling algorithm:
    next_push_time = now + random(min_interval_hours, max_interval_hours)
    if next_push_time is outside [active_hours_start, active_hours_end]:
        -> shift to the next day's active_hours_start + random(0, 120min) offset
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from octop.infra.db.repos.care_push import CarePushRepo
    from octop.infra.db.repos.proactive_care_config import (
        ProactiveCareConfigRepo,
    )
    from octop.infra.db.repos.sessions import SessionRepo
    from octop.infra.proactive.service import ProactiveCareService

logger = logging.getLogger(__name__)


def _parse_hhmm(hhmm: str) -> time:
    """Parse an HH:MM time string."""
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def compute_next_trigger(
    *,
    now: datetime,
    active_hours_start: str,
    active_hours_end: str,
    min_interval_hours: int,
    max_interval_hours: int,
) -> datetime:
    """Compute the next trigger time.

    Algorithm:
    1. Pick a random interval within [min_interval_hours, max_interval_hours].
    2. Compute candidate time = now + random interval.
    3. If the candidate falls within active hours, return it directly.
    4. Otherwise shift to the next active-hours start + random(0, 120min).

    Args:
        now: Current time (UTC).
        active_hours_start: Active-hours start (HH:MM).
        active_hours_end: Active-hours end (HH:MM).
        min_interval_hours: Minimum interval (hours).
        max_interval_hours: Maximum interval (hours).

    Returns:
        The next trigger time (UTC).
    """
    # Pick a random interval (minute precision)
    interval_minutes = random.randint(
        min_interval_hours * 60,
        max_interval_hours * 60,
    )
    candidate = now + timedelta(minutes=interval_minutes)

    start_t = _parse_hhmm(active_hours_start)
    end_t = _parse_hhmm(active_hours_end)

    # Check whether the candidate falls within active hours (compare hour/minute of local time)
    # Note: we compare using the UTC time's hour/minute; a timezone conversion may be
    # needed in real deployments, but since config has no timezone field we use UTC for now.
    candidate_t = candidate.time().replace(second=0, microsecond=0)

    if start_t <= candidate_t < end_t:
        return candidate

    # Outside active hours -> shift to next active-hours start + random(0, 120min)
    random_offset_minutes = random.randint(0, 120)

    # Find the start of the next active-hours window
    # First try today's active_hours_start
    today = candidate.date()
    today_start = datetime.combine(today, start_t, tzinfo=UTC)
    if today_start > candidate:
        # Today's active hours have not started yet; use today's
        next_start = today_start
    else:
        # Today's active hours have already passed; use tomorrow's
        tomorrow = today + timedelta(days=1)
        next_start = datetime.combine(tomorrow, start_t, tzinfo=UTC)

    return next_start + timedelta(minutes=random_offset_minutes)


def is_in_active_hours(
    now: datetime,
    *,
    active_hours_start: str,
    active_hours_end: str,
) -> bool:
    """Check whether the current time is within the active hours."""
    start_t = _parse_hhmm(active_hours_start)
    end_t = _parse_hhmm(active_hours_end)
    current_t = now.time().replace(second=0, microsecond=0)
    return start_t <= current_t < end_t


class ProactiveCareScheduler:
    """Proactive care push random scheduler.

    After each push completes, immediately schedule the next push time at random.

    Args:
        care_service: ProactiveCareService instance.
        config_repo: ProactiveCareConfigRepo instance.
        session_repo: SessionRepo instance, used to obtain the agent's active session.
    """

    def __init__(
        self,
        *,
        care_service: ProactiveCareService,
        config_repo: ProactiveCareConfigRepo,
        session_repo: SessionRepo,
    ) -> None:
        self._care_service = care_service
        self._config_repo = config_repo
        self._session_repo = session_repo
        # agent_id -> asyncio.Task
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def replace_persistence(
        self,
        *,
        config_repo: ProactiveCareConfigRepo,
        session_repo: SessionRepo,
        care_push_repo: CarePushRepo,
    ) -> None:
        """Point scheduler/care persistence at a rebound control-plane pool."""
        self._config_repo = config_repo
        self._session_repo = session_repo
        self._care_service.replace_care_push_repo(care_push_repo)

    async def start_all(self) -> None:
        """At system startup, register random scheduling tasks for all agents with enabled=true."""
        configs = self._config_repo.list_enabled()
        logger.info("ProactiveCareScheduler: started, found %d enabled agents", len(configs))
        for cfg in configs:
            self._schedule(cfg.agent_id)

    def reschedule(self, agent_id: str) -> None:
        """Cancel the current schedule and re-arrange the next trigger time with new config.

        Usually called after the user updates the configuration.

        Args:
            agent_id: The agent ID to reschedule.
        """
        self.cancel(agent_id)
        cfg = self._config_repo.get(agent_id)
        if cfg.enabled:
            self._schedule(agent_id)
            logger.info("ProactiveCareScheduler: agent=%s rescheduled (enabled=true)", agent_id)
        else:
            logger.info(
                "ProactiveCareScheduler: agent=%s schedule cancelled (enabled=false)", agent_id
            )

    def cancel(self, agent_id: str) -> None:
        """Cancel an agent's scheduling task.

        Args:
            agent_id: The agent ID to cancel.
        """
        task = self._tasks.pop(agent_id, None)
        if task and not task.done():
            task.cancel()

    async def shutdown(self) -> None:
        """Shut down all scheduling tasks."""
        agent_ids = list(self._tasks.keys())
        for agent_id in agent_ids:
            self.cancel(agent_id)
        logger.info("ProactiveCareScheduler: all scheduled tasks shut down")

    def _schedule(self, agent_id: str) -> None:
        """Create a scheduling task for an agent."""
        task = asyncio.create_task(
            self._run_loop(agent_id),
            name=f"proactive_care_{agent_id}",
        )
        self._tasks[agent_id] = task
        task.add_done_callback(lambda t: self._on_task_done(agent_id, t))

    def _on_task_done(self, agent_id: str, task: asyncio.Task[None]) -> None:
        """Task-completion callback that handles exceptions."""
        self._tasks.pop(agent_id, None)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(
                "ProactiveCareScheduler: agent=%s scheduler task exited with error: %s",
                agent_id,
                exc,
                exc_info=exc,
            )

    async def _run_loop(self, agent_id: str) -> None:
        """The scheduling loop for a single agent.

        After each push completes, immediately compute the next trigger time and wait.
        """
        logger.info("ProactiveCareScheduler: agent=%s scheduler loop started", agent_id)
        while True:
            cfg = self._config_repo.get(agent_id)
            if not cfg.enabled:
                logger.info(
                    "ProactiveCareScheduler: agent=%s enabled=false, exiting scheduler loop",
                    agent_id,
                )
                return

            now = datetime.now(UTC)

            # Compute the next trigger time
            next_trigger = compute_next_trigger(
                now=now,
                active_hours_start=cfg.active_hours_start,
                active_hours_end=cfg.active_hours_end,
                min_interval_hours=cfg.min_interval_hours,
                max_interval_hours=cfg.max_interval_hours,
            )

            wait_seconds = (next_trigger - now).total_seconds()
            logger.info(
                "ProactiveCareScheduler: agent=%s next push at %s (waiting %.0f s)",
                agent_id,
                next_trigger.strftime("%Y-%m-%d %H:%M UTC"),
                wait_seconds,
            )

            # Wait until the next trigger time
            # Anti-busy-loop guard: if the interval is too short (< 60s), force a 60s wait to avoid CPU spinning
            _MIN_SLEEP_SECONDS = 60
            if wait_seconds < _MIN_SLEEP_SECONDS:
                logger.warning(
                    "ProactiveCareScheduler: agent=%s computed wait too short (%.0f s), "
                    "forcing %d s wait; check min_interval_hours config",
                    agent_id,
                    wait_seconds,
                    _MIN_SLEEP_SECONDS,
                )
                wait_seconds = _MIN_SLEEP_SECONDS
            await asyncio.sleep(wait_seconds)

            # Re-check the enabled state (the agent may have been disabled during the wait)
            cfg = self._config_repo.get(agent_id)
            if not cfg.enabled:
                logger.info(
                    "ProactiveCareScheduler: agent=%s disabled during wait, skipping this push",
                    agent_id,
                )
                return

            # Check whether the current time is within active hours
            now = datetime.now(UTC)
            if not is_in_active_hours(
                now,
                active_hours_start=cfg.active_hours_start,
                active_hours_end=cfg.active_hours_end,
            ):
                logger.info(
                    "ProactiveCareScheduler: agent=%s current time outside active hours, skipping this push",
                    agent_id,
                )
                continue  # go straight to the next loop iteration and recompute the next trigger

            # Get the agent's active session
            sessions = self._session_repo.list_by_agent(agent_id, limit=10)
            if not sessions:
                logger.info(
                    "ProactiveCareScheduler: agent=%s has no active session, skipping this push",
                    agent_id,
                )
                continue

            # Prefer an IM session (non-empty channel_id), otherwise pick the most recently active session
            target_session = next(
                (s for s in sessions if s.channel_id),
                sessions[0],
            )

            # Perform the push
            try:
                await self._care_service.run(agent_id, target_session.session_key)
            except Exception as exc:
                logger.error(
                    "ProactiveCareScheduler: agent=%s push error: %s",
                    agent_id,
                    exc,
                    exc_info=exc,
                )
            # Regardless of success or failure, continue to the next scheduling round
