"""CronManager — process-wide singleton that owns all user-defined scheduled CronJob instances."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from octop.infra.cron.job import CronJob
from octop.infra.cron.trigger import build_trigger
from octop.infra.db.repos.audit import ACTOR_SYSTEM
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.threads import ThreadRegistry

if TYPE_CHECKING:
    from octop.infra.db.repos.cron import CronJobRow
    from octop.infra.db.services import RepoBundle
    from octop.infra.gateway.gateway import Gateway

from octop.infra.cron.task_type import normalize_cron_task_type
from octop.infra.db.repos._base import UNSET

logger = logging.getLogger(__name__)


@dataclass
class CronCreateSpec:
    """Input spec for creating a new cron job."""

    cron_id: str
    agent_id: str
    user_id: int
    trigger: str
    prompt: str
    session_key: str | None = None
    fresh_thread: bool = False
    model: str | None = None
    task_type: str = "agent"
    enabled: bool = True
    meta: dict[str, Any] = field(default_factory=dict)
    username: str | None = None


class CronManager:
    """Process-wide singleton: owns APScheduler + all CronJob instances."""

    def __init__(
        self,
        *,
        gateway: Gateway,
        repos: RepoBundle,
        timezone: str = "Asia/Shanghai",
    ) -> None:
        self._gateway = gateway
        self._repos = repos
        self._timezone = timezone
        self._scheduler: AsyncIOScheduler = AsyncIOScheduler(timezone=timezone)
        self._lock = asyncio.Lock()

    def replace_repos(self, repos: RepoBundle) -> None:
        """Point cron persistence at a rebound control-plane pool."""
        self._repos = repos

    async def boot(self) -> None:
        self._scheduler.start()
        rows = self._repos.cron_repo.list_all(include_disabled=False)
        for row in rows:
            self._schedule(row)
        logger.info("CronManager booted; scheduled %d jobs", len(rows))

    async def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("CronManager shut down")

    async def create(self, spec: CronCreateSpec | None = None, **kwargs: Any) -> CronJobRow:
        if spec is None:
            spec = CronCreateSpec(**kwargs)
        build_trigger(spec.trigger)
        session_key = spec.session_key or ThreadRegistry.dashboard_key(
            agent_id=spec.agent_id,
            user_id=spec.user_id,
        )
        await self._ensure_session(
            session_key,
            agent_id=spec.agent_id,
            user_id=spec.user_id,
        )
        async with self._lock:
            self._repos.cron_repo.create(
                cron_id=spec.cron_id,
                agent_id=spec.agent_id,
                user_id=spec.user_id,
                trigger=spec.trigger,
                prompt=spec.prompt,
                session_key=session_key,
                fresh_thread=spec.fresh_thread,
                model=(spec.model or "").strip() or None,
                task_type=normalize_cron_task_type(spec.task_type),
            )
            row = self._repos.cron_repo.get(spec.cron_id)
            assert row is not None
            if spec.enabled:
                self._schedule(row)
            self._repos.audit_repo.write(
                actor=spec.username or str(spec.user_id),
                action="cron.create",
                target=spec.cron_id,
                payload=spec.prompt[:80],
            )
            logger.info("CronJob %s created for agent %s", spec.cron_id, spec.agent_id)
            return row

    def get(self, cron_id: str) -> CronJobRow | None:
        return self._repos.cron_repo.get(cron_id)

    def list_by_agent(self, agent_id: str, *, include_disabled: bool = True) -> list[CronJobRow]:
        return self._repos.cron_repo.list_by_agent(agent_id, include_disabled=include_disabled)

    def list_all(self, *, include_disabled: bool = True) -> list[CronJobRow]:
        return self._repos.cron_repo.list_all(include_disabled=include_disabled)

    async def update(
        self,
        cron_id: str,
        *,
        trigger: str | None = None,
        prompt: str | None = None,
        session_key: str | None = None,
        fresh_thread: bool | None = None,
        enabled: int | None = None,
        task_type: str | None = None,
        model: str | None | object = UNSET,
    ) -> CronJobRow:
        if trigger is not None:
            build_trigger(trigger)
        enabled_bool: bool | None = bool(enabled) if enabled is not None else None
        async with self._lock:
            existing = self._repos.cron_repo.get(cron_id)
            if existing is None:
                raise OctopError(ErrorCode.NOT_FOUND, f"cron job {cron_id!r} not found")
            repo_kwargs: dict[str, Any] = {
                "trigger": trigger,
                "prompt": prompt,
                "session_key": session_key,
                "fresh_thread": fresh_thread,
                "enabled": enabled_bool,
            }
            if task_type is not None:
                repo_kwargs["task_type"] = normalize_cron_task_type(task_type)
            if model is not UNSET:
                raw = model if isinstance(model, str) else None
                repo_kwargs["model"] = (raw or "").strip() or None
            self._repos.cron_repo.update(cron_id, **repo_kwargs)
            row = self._repos.cron_repo.get(cron_id)
            if row is None:
                raise OctopError(ErrorCode.NOT_FOUND, f"cron job {cron_id!r} not found")
            self._unschedule(cron_id)
            if row.enabled:
                self._schedule(row)
            logger.info("CronJob %s updated", cron_id)
            return row

    async def delete(self, cron_id: str) -> None:
        async with self._lock:
            self._unschedule(cron_id)
            self._repos.cron_repo.delete(cron_id)
            self._repos.audit_repo.write(actor=ACTOR_SYSTEM, action="cron.delete", target=cron_id)
            logger.info("CronJob %s deleted", cron_id)

    async def run_now(self, cron_id: str) -> None:
        row = self._repos.cron_repo.get(cron_id)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, f"cron job {cron_id!r} not found")
        job = self._make_job(row)
        asyncio.ensure_future(job.run())
        logger.info("CronJob %s triggered manually", cron_id)

    def _make_job(self, row: Any) -> CronJob:
        return CronJob.from_row(
            row,
            gateway=self._gateway,
            cron_repo=self._repos.cron_repo,
            audit_repo=self._repos.audit_repo,
        )

    def _schedule(self, row: Any) -> None:
        if not row.enabled:
            return
        try:
            trigger = build_trigger(row.trigger)
        except OctopError:
            logger.warning(
                "CronJob %s has invalid trigger %r; skipping schedule",
                row.cron_id,
                row.trigger,
            )
            return
        job = self._make_job(row)
        if self._scheduler.get_job(row.cron_id):
            self._scheduler.remove_job(row.cron_id)
        self._scheduler.add_job(
            job.run,
            trigger=trigger,
            id=row.cron_id,
            replace_existing=True,
            misfire_grace_time=60,
        )

    def _unschedule(self, cron_id: str) -> None:
        if self._scheduler.get_job(cron_id):
            self._scheduler.remove_job(cron_id)

    async def _ensure_session(self, session_key: str, *, agent_id: str, user_id: int) -> None:
        registry = self._gateway.thread_registry
        existing = registry.get_session(session_key)
        if existing is not None:
            if existing.agent_id != agent_id:
                msg = (
                    f"session {session_key!r} belongs to agent {existing.agent_id!r}, "
                    f"not {agent_id!r}"
                )
                raise ValueError(msg)
            return
        parts = session_key.split(":", 3)
        channel_type = parts[1] if len(parts) >= 2 else "cron"
        chat_type = parts[3] if len(parts) >= 4 else ThreadRegistry.CHAT_TYPE_DM
        await registry.get_or_create_by_key(
            session_key=session_key,
            agent_id=agent_id,
            user_id=user_id,
            channel_type=channel_type,
            channel_chat_type=chat_type,
        )

    def schedule_system_job(self, job_id: str, *, trigger: str, func: Any) -> None:
        """Register a process-level job that is not stored in the cron DB."""
        built = build_trigger(trigger)
        self._scheduler.add_job(
            func,
            trigger=built,
            id=job_id,
            replace_existing=True,
            misfire_grace_time=300,
        )
