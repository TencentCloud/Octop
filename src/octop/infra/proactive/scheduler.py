"""ProactiveCareScheduler — when to send a proactive care message.

Spacing still comes from a random gap in ``[min_interval_hours, max_interval_hours]``.
The moment itself follows the same gates as finnie's proactivity check:

- stay inside the configured care window, including a window that crosses midnight
- if the sampled instant misses the window, wait until that window next opens
- do not speak while the agent is in a user-visible turn
- do not speak until the conversation has been quiet for ``_IDLE_HOURS``
- a care push of our own does not count as the user coming back
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if TYPE_CHECKING:
    from octop.infra.db.repos.agents import AgentRepo
    from octop.infra.db.repos.care_push import CarePushRepo
    from octop.infra.db.repos.proactive_care_config import (
        ProactiveCareConfig,
        ProactiveCareConfigRepo,
    )
    from octop.infra.db.repos.sessions import SessionRepo
    from octop.infra.db.repos.threads import ThreadRepo
    from octop.infra.db.repos.users import UserRepo
    from octop.infra.proactive.service import ProactiveCareService
from octop.infra.users.preferences import get_timezone_from_preferences_json

_UTC_TZ_NAME = "UTC"

logger = logging.getLogger(__name__)

# Finnie waits ``idle_hours`` (default 4) after the last user turn. A care we
# just sent must not restart that clock.
_IDLE_HOURS = 4.0
_PUSH_ACTIVITY_SLACK = timedelta(minutes=5)
_BUSY_RETRY = timedelta(minutes=15)
# Smear only the "window just opened" wake so agents don't all fire on the minute.
_OPEN_JITTER_MINUTES = 15


def _parse_hhmm(hhmm: str) -> time:
    """Parse an HH:MM time string."""
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def _clock_in_window(current: time, start: time, end: time) -> bool:
    """Return whether ``current`` sits in ``[start, end)``.

    A window whose end is earlier than its start crosses midnight: 22:00–08:00
    covers the evening and the following morning, and excludes 08:00 itself.
    """
    if start == end:
        return False
    if start < end:
        return start <= current < end
    return current >= start or current < end


def _floor_minute(moment: datetime) -> datetime:
    return moment.replace(second=0, microsecond=0)


def _window_containing_or_next(
    local: datetime,
    start_t: time,
    end_t: time,
) -> tuple[datetime, datetime]:
    """Return ``[start, end)`` for the window that contains ``local``, or the next one."""
    tz = local.tzinfo
    day = local.date()
    if start_t < end_t:
        start = datetime.combine(day, start_t, tzinfo=tz)
        end = datetime.combine(day, end_t, tzinfo=tz)
        if local >= end:
            start += timedelta(days=1)
            end += timedelta(days=1)
        return start, end

    start_today = datetime.combine(day, start_t, tzinfo=tz)
    end_today = datetime.combine(day, end_t, tzinfo=tz)
    if local < end_today:
        return start_today - timedelta(days=1), end_today
    if local >= start_today:
        return start_today, end_today + timedelta(days=1)
    return start_today, end_today + timedelta(days=1)


def next_window_opening(
    not_before: datetime,
    *,
    active_hours_start: str,
    active_hours_end: str,
    timezone_name: str = _UTC_TZ_NAME,
) -> datetime:
    """Earliest legal moment at or after ``not_before``, with a short open jitter.

    Used when a deferred care (user still chatting, or we woke outside hours)
    should go out as soon as the window allows, rather than being re-rolled
    across the whole day.
    """
    timezone = _resolve_timezone(timezone_name)
    local = _floor_minute(not_before.astimezone(timezone))
    start_t = _parse_hhmm(active_hours_start)
    end_t = _parse_hhmm(active_hours_end)
    if _clock_in_window(local.time(), start_t, end_t):
        return local.astimezone(UTC)

    start, end = _window_containing_or_next(local, start_t, end_t)
    span = int((end - start).total_seconds() // 60)
    jitter_cap = min(_OPEN_JITTER_MINUTES, max(span - 1, 0))
    jitter = random.randint(0, jitter_cap) if jitter_cap else 0
    jitter = max(0, min(jitter, jitter_cap))
    return (start + timedelta(minutes=jitter)).astimezone(UTC)


def compute_next_trigger(
    *,
    now: datetime,
    active_hours_start: str,
    active_hours_end: str,
    min_interval_hours: int,
    max_interval_hours: int,
    timezone_name: str = _UTC_TZ_NAME,
) -> datetime:
    """Compute the next trigger time.

    Draw a gap in ``[min_interval_hours, max_interval_hours]``. If that instant
    is inside care hours, use it. If it misses, move it to the next opening of
    the care window. A short jitter keeps every agent from firing on the same
    minute, and it stays inside the window.

    Args:
        now: Current time (UTC).
        active_hours_start: Active-hours start (HH:MM).
        active_hours_end: Active-hours end (HH:MM).
        min_interval_hours: Minimum interval (hours).
        max_interval_hours: Maximum interval (hours).
        timezone_name: IANA timezone used for the care-window check.

    Returns:
        The next trigger time (UTC).
    """
    local_now = now.astimezone(_resolve_timezone(timezone_name))
    interval_minutes = random.randint(
        min_interval_hours * 60,
        max_interval_hours * 60,
    )
    candidate = _floor_minute(local_now + timedelta(minutes=interval_minutes))
    start_t = _parse_hhmm(active_hours_start)
    end_t = _parse_hhmm(active_hours_end)
    if _clock_in_window(candidate.time(), start_t, end_t):
        return candidate.astimezone(UTC)
    return next_window_opening(
        candidate,
        active_hours_start=active_hours_start,
        active_hours_end=active_hours_end,
        timezone_name=timezone_name,
    )


def is_in_active_hours(
    now: datetime,
    *,
    active_hours_start: str,
    active_hours_end: str,
    timezone_name: str = _UTC_TZ_NAME,
) -> bool:
    """Check whether the current time is within the active hours."""
    local = now.astimezone(_resolve_timezone(timezone_name))
    current_t = local.time().replace(second=0, microsecond=0)
    return _clock_in_window(
        current_t,
        _parse_hhmm(active_hours_start),
        _parse_hhmm(active_hours_end),
    )


def idle_ready_at(
    *,
    now: datetime,
    last_active_at: int | None,
    last_push_at: int | None,
    idle_hours: float = _IDLE_HOURS,
) -> datetime | None:
    """Return when the user will have been quiet long enough, or None if they already are.

    ``last_active_at`` is the latest thread touch. A touch within
    ``_PUSH_ACTIVITY_SLACK`` of our own care push is the push itself, not the
    user coming back, and does not restart the idle clock.
    """
    if not last_active_at or last_active_at <= 0:
        return None
    if last_push_at is not None:
        slack = int(_PUSH_ACTIVITY_SLACK.total_seconds())
        if last_active_at <= last_push_at + slack:
            return None
    quiet_at = datetime.fromtimestamp(last_active_at, tz=UTC) + timedelta(hours=idle_hours)
    if quiet_at <= now:
        return None
    return quiet_at


class TimingDecision:
    """Whether to send now, or the UTC instant to reconsider."""

    __slots__ = ("retry_at", "send")

    def __init__(self, *, send: bool, retry_at: datetime | None = None) -> None:
        self.send = send
        self.retry_at = retry_at


def decide_send_timing(
    *,
    now: datetime,
    active_hours_start: str,
    active_hours_end: str,
    timezone_name: str = _UTC_TZ_NAME,
    last_active_at: int | None = None,
    last_push_at: int | None = None,
    agent_busy: bool = False,
    idle_hours: float = _IDLE_HOURS,
) -> TimingDecision:
    """Apply finnie's send gates once a scheduled wake actually arrives.

    Outside the care window, wait until it opens. Inside it, yield to an
    in-progress turn and to a conversation that has not been quiet for
    ``idle_hours``. A deferral does not draw a new min/max gap.
    """
    hours = {
        "active_hours_start": active_hours_start,
        "active_hours_end": active_hours_end,
        "timezone_name": timezone_name,
    }
    if not is_in_active_hours(now, **hours):
        return TimingDecision(send=False, retry_at=next_window_opening(now, **hours))
    if agent_busy:
        return TimingDecision(send=False, retry_at=now + _BUSY_RETRY)
    quiet_at = idle_ready_at(
        now=now,
        last_active_at=last_active_at,
        last_push_at=last_push_at,
        idle_hours=idle_hours,
    )
    if quiet_at is None:
        return TimingDecision(send=True)
    if is_in_active_hours(quiet_at, **hours):
        return TimingDecision(send=False, retry_at=quiet_at)
    return TimingDecision(send=False, retry_at=next_window_opening(quiet_at, **hours))


def _resolve_timezone(timezone_name: str) -> ZoneInfo:
    """Resolve timezone with UTC fallback."""
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo(_UTC_TZ_NAME)


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
        agent_repo: AgentRepo | None = None,
        user_repo: UserRepo | None = None,
        thread_repo: ThreadRepo | None = None,
        care_push_repo: CarePushRepo | None = None,
        is_agent_busy: Callable[[str], bool] | None = None,
        default_timezone: str = _UTC_TZ_NAME,
    ) -> None:
        self._care_service = care_service
        self._config_repo = config_repo
        self._session_repo = session_repo
        self._agent_repo = agent_repo
        self._user_repo = user_repo
        self._thread_repo = thread_repo
        self._care_push_repo = care_push_repo
        self._is_agent_busy = is_agent_busy
        self._default_timezone = default_timezone
        # agent_id -> asyncio.Task
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._suspended = False

    def replace_persistence(
        self,
        *,
        config_repo: ProactiveCareConfigRepo,
        session_repo: SessionRepo,
        care_push_repo: CarePushRepo,
        thread_repo: ThreadRepo | None = None,
    ) -> None:
        """Point scheduler/care persistence at a rebound control-plane pool."""
        self._config_repo = config_repo
        self._session_repo = session_repo
        self._care_push_repo = care_push_repo
        if thread_repo is not None:
            self._thread_repo = thread_repo
        self._care_service.replace_care_push_repo(care_push_repo)

    async def start_all(self) -> None:
        """At system startup, register random scheduling tasks for all agents with enabled=true.

        Includes agents that never saved a config row: proactive care defaults to on.
        """
        configs = self._config_repo.list_enabled()
        logger.info("ProactiveCareScheduler: started, found %d enabled agents", len(configs))
        for cfg in configs:
            self.ensure_scheduled(cfg.agent_id)

    def suspend(self) -> None:
        """Stop creating new loops. Tests call this so leftover sleeps do not hang pytest."""
        self._suspended = True

    def ensure_scheduled(self, agent_id: str) -> None:
        """Start the loop if this agent is enabled and not already scheduled."""
        if self._suspended:
            return
        if agent_id in self._tasks:
            return
        cfg = self._config_repo.get(agent_id)
        if cfg.enabled:
            self._schedule(agent_id)
            logger.info(
                "ProactiveCareScheduler: agent=%s scheduled (default enabled unless opted out)",
                agent_id,
            )

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
        """Cancel every loop and wait so a long sleep cannot outlive the process."""
        pending: list[asyncio.Task[None]] = []
        for agent_id in list(self._tasks.keys()):
            task = self._tasks.pop(agent_id, None)
            if task and not task.done():
                task.cancel()
                pending.append(task)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        logger.info("ProactiveCareScheduler: all scheduled tasks shut down")

    def _schedule(self, agent_id: str) -> None:
        """Create a scheduling task for an agent."""
        if self._suspended:
            return
        existing = self._tasks.get(agent_id)
        if existing is not None and not existing.done():
            existing.cancel()
        task = asyncio.create_task(
            self._run_loop(agent_id),
            name=f"proactive_care_{agent_id}",
        )
        self._tasks[agent_id] = task
        task.add_done_callback(lambda t: self._on_task_done(agent_id, t))

    def _on_task_done(self, agent_id: str, task: asyncio.Task[None]) -> None:
        """Task-completion callback that handles exceptions."""
        if self._tasks.get(agent_id) is task:
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
        # None means "draw a fresh min/max gap". A datetime means "reconsider then",
        # which is how idle and busy defers avoid burning another full interval.
        hold_until: datetime | None = None
        while True:
            cfg = self._config_repo.get(agent_id)
            if not cfg.enabled:
                logger.info(
                    "ProactiveCareScheduler: agent=%s enabled=false, exiting scheduler loop",
                    agent_id,
                )
                return

            now = datetime.now(UTC)
            timezone_name = self._resolve_tz_for_agent(agent_id)

            if hold_until is None:
                hold_until = compute_next_trigger(
                    now=now,
                    active_hours_start=cfg.active_hours_start,
                    active_hours_end=cfg.active_hours_end,
                    min_interval_hours=cfg.min_interval_hours,
                    max_interval_hours=cfg.max_interval_hours,
                    timezone_name=timezone_name,
                )
                wait_seconds = (hold_until - now).total_seconds()
                # Anti-busy-loop guard for a gap that collapsed below a minute.
                _MIN_SLEEP_SECONDS = 60
                if wait_seconds < _MIN_SLEEP_SECONDS:
                    logger.warning(
                        "ProactiveCareScheduler: agent=%s computed wait too short (%.0f s), "
                        "forcing %d s wait; check min_interval_hours config",
                        agent_id,
                        wait_seconds,
                        _MIN_SLEEP_SECONDS,
                    )
                    hold_until = now + timedelta(seconds=_MIN_SLEEP_SECONDS)
                    wait_seconds = _MIN_SLEEP_SECONDS
            else:
                wait_seconds = (hold_until - now).total_seconds()

            if wait_seconds > 0:
                logger.info(
                    "ProactiveCareScheduler: agent=%s next check at %s (waiting %.0f s)",
                    agent_id,
                    hold_until.astimezone(_resolve_timezone(timezone_name)).strftime(
                        "%Y-%m-%d %H:%M %Z"
                    ),
                    wait_seconds,
                )
                await asyncio.sleep(wait_seconds)

            cfg = self._config_repo.get(agent_id)
            if not cfg.enabled:
                logger.info(
                    "ProactiveCareScheduler: agent=%s disabled during wait, skipping this push",
                    agent_id,
                )
                return

            now = datetime.now(UTC)
            decision = self._timing_decision(agent_id, cfg, timezone_name, now)
            if not decision.send:
                hold_until = decision.retry_at
                if hold_until is None or hold_until <= now:
                    hold_until = now + timedelta(seconds=60)
                logger.info(
                    "ProactiveCareScheduler: agent=%s not a good moment, next check at %s",
                    agent_id,
                    hold_until.isoformat() if hold_until is not None else "unset",
                )
                continue

            sessions = self._session_repo.list_by_agent(agent_id, limit=10)
            if not sessions:
                logger.info(
                    "ProactiveCareScheduler: agent=%s has no active session, skipping this push",
                    agent_id,
                )
                hold_until = None
                continue

            # Prefer an IM session (non-empty channel_id), otherwise the most recently active one.
            target_session = next(
                (s for s in sessions if s.channel_id),
                sessions[0],
            )

            def can_send(
                bound_cfg: ProactiveCareConfig = cfg,
                bound_tz: str = timezone_name,
            ) -> bool:
                return self._moment_is_good(agent_id, bound_cfg, bound_tz)

            try:
                await self._care_service.run(
                    agent_id,
                    target_session.session_key,
                    can_send=can_send,
                )
            except Exception as exc:
                logger.error(
                    "ProactiveCareScheduler: agent=%s push error: %s",
                    agent_id,
                    exc,
                    exc_info=exc,
                )
            hold_until = None

    def _timing_decision(
        self,
        agent_id: str,
        cfg: ProactiveCareConfig,
        timezone_name: str,
        now: datetime,
    ) -> TimingDecision:
        return decide_send_timing(
            now=now,
            active_hours_start=cfg.active_hours_start,
            active_hours_end=cfg.active_hours_end,
            timezone_name=timezone_name,
            last_active_at=self._latest_activity(agent_id),
            last_push_at=self._latest_push(agent_id),
            agent_busy=self._agent_is_busy(agent_id),
        )

    def _moment_is_good(
        self,
        agent_id: str,
        cfg: ProactiveCareConfig,
        timezone_name: str,
    ) -> bool:
        return self._timing_decision(agent_id, cfg, timezone_name, datetime.now(UTC)).send

    def _latest_activity(self, agent_id: str) -> int | None:
        if self._thread_repo is None:
            return None
        try:
            return self._thread_repo.latest_user_activity(agent_id)
        except Exception:
            logger.warning(
                "ProactiveCareScheduler: agent=%s failed to read last activity",
                agent_id,
                exc_info=True,
            )
            return None

    def _latest_push(self, agent_id: str) -> int | None:
        if self._care_push_repo is None:
            return None
        try:
            return self._care_push_repo.latest_pushed_at(agent_id)
        except Exception:
            logger.warning(
                "ProactiveCareScheduler: agent=%s failed to read last care push",
                agent_id,
                exc_info=True,
            )
            return None

    def _agent_is_busy(self, agent_id: str) -> bool:
        if self._is_agent_busy is None:
            return False
        try:
            return self._is_agent_busy(agent_id) is True
        except Exception:
            logger.warning(
                "ProactiveCareScheduler: agent=%s failed to read busy state",
                agent_id,
                exc_info=True,
            )
            return False

    def _resolve_tz_for_agent(self, agent_id: str) -> str:
        if self._agent_repo is None or self._user_repo is None:
            return self._default_timezone

        agent = self._agent_repo.get(agent_id)
        if agent is None or agent.user_id is None:
            return self._default_timezone

        user = self._user_repo.get(agent.user_id)
        if user is None:
            return self._default_timezone

        timezone_name = get_timezone_from_preferences_json(user.preferences_json)
        if not timezone_name:
            return self._default_timezone

        try:
            ZoneInfo(timezone_name)
            return timezone_name
        except ZoneInfoNotFoundError:
            return self._default_timezone
