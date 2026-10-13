"""CronManager — process-wide singleton that owns all user-defined scheduled CronJob instances."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from octop.i18n import tr
from octop.infra.connectors.crypto import decrypt_credentials
from octop.infra.connectors.gateway.adapters.agently_cli import read_auth_status
from octop.infra.connectors.gateway.agently_watch import AgentlyWatchManager
from octop.infra.cron.delivery import CronDeliveryService
from octop.infra.cron.job import CronJob
from octop.infra.cron.trigger import AgentlyMailTrigger, build_trigger
from octop.infra.db.repos.audit import ACTOR_SYSTEM
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.locale import resolve_user_locale

if TYPE_CHECKING:
    from octop.infra.db.repos.connectors import ConnectorRow
    from octop.infra.db.repos.cron import CronJobRow
    from octop.infra.db.services import RepoBundle
    from octop.infra.gateway.gateway import Gateway

from octop.infra.cron.task_type import normalize_cron_task_type, require_cron_name
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
    name: str | None = None
    session_key: str | None = None
    fresh_thread: bool = False
    model: str | None = None
    task_type: str = "agent"
    mcp_servers: list[str] = field(default_factory=list)
    enabled: bool = True
    meta: dict[str, Any] = field(default_factory=dict)
    username: str | None = None


class CronManager:
    """Process-wide singleton: owns APScheduler + all CronJob instances."""

    def __init__(
        self,
        *,
        gateway: Gateway,
        delivery_service: CronDeliveryService,
        repos: RepoBundle,
        timezone: str = "Asia/Shanghai",
    ) -> None:
        self._gateway = gateway
        self._delivery_service = delivery_service
        self._repos = repos
        self._timezone = timezone
        self._scheduler: AsyncIOScheduler = AsyncIOScheduler(timezone=timezone)
        self._lock = asyncio.Lock()
        self._mail_watch = AgentlyWatchManager()
        # Process-level jobs (e.g. TLS auto-renew) that must survive reload_from_db.
        self._system_job_ids: set[str] = set()

    def replace_repos(self, repos: RepoBundle) -> None:
        """Point cron persistence at a rebound control-plane pool."""
        self._repos = repos
        self._delivery_service.replace_repos(repos)

    async def boot(self) -> None:
        self._scheduler.start()
        rows = self._repos.cron_repo.list_all(include_disabled=False)
        for row in rows:
            self._schedule(row)
        logger.info("CronManager booted; scheduled %d jobs", len(rows))

    async def reload_from_db(self) -> None:
        """Drop user cron schedules and re-register enabled jobs from the DB.

        Used after backup/migration restore so APScheduler matches the replaced
        ``cron_jobs`` table without a process restart. System jobs registered via
        :meth:`schedule_system_job` are left in place.
        """
        async with self._lock:
            await self._mail_watch.close()
            for job in list(self._scheduler.get_jobs()):
                job_id = getattr(job, "id", None)
                if job_id is None or job_id in self._system_job_ids:
                    continue
                self._scheduler.remove_job(job_id)
            rows = self._repos.cron_repo.list_all(include_disabled=False)
            for row in rows:
                self._schedule(row)
            logger.info("CronManager reloaded from DB; scheduled %d jobs", len(rows))

    async def shutdown(self) -> None:
        await self._mail_watch.close()
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("CronManager shut down")

    async def create(self, spec: CronCreateSpec | None = None, **kwargs: Any) -> CronJobRow:
        if spec is None:
            spec = CronCreateSpec(**kwargs)
        self._mail_source(spec.trigger, spec.user_id)
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
                name=require_cron_name(spec.name, prompt=spec.prompt, cron_id=spec.cron_id),
                trigger=spec.trigger,
                prompt=spec.prompt,
                session_key=session_key,
                fresh_thread=spec.fresh_thread,
                model=(spec.model or "").strip() or None,
                task_type=normalize_cron_task_type(spec.task_type),
                mcp_servers=list(spec.mcp_servers or []),
                enabled=spec.enabled,
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

    def list_by_agent(
        self,
        agent_id: str,
        *,
        include_disabled: bool = True,
        user_id: int | None = None,
    ) -> list[CronJobRow]:
        return self._repos.cron_repo.list_by_agent(
            agent_id,
            include_disabled=include_disabled,
            user_id=user_id,
        )

    def list_all(self, *, include_disabled: bool = True) -> list[CronJobRow]:
        return self._repos.cron_repo.list_all(include_disabled=include_disabled)

    async def update(
        self,
        cron_id: str,
        *,
        trigger: str | None = None,
        name: str | None = None,
        prompt: str | None = None,
        session_key: str | None = None,
        fresh_thread: bool | None = None,
        enabled: int | None = None,
        task_type: str | None = None,
        model: str | None | object = UNSET,
        mcp_servers: list[str] | None | object = UNSET,
    ) -> CronJobRow:
        enabled_bool: bool | None = bool(enabled) if enabled is not None else None
        async with self._lock:
            existing = self._repos.cron_repo.get(cron_id)
            if existing is None:
                raise OctopError(ErrorCode.NOT_FOUND, f"cron job {cron_id!r} not found")
            if trigger is not None or enabled_bool is True:
                self._mail_source(trigger or existing.trigger, existing.user_id)
            repo_kwargs: dict[str, Any] = {
                "trigger": trigger,
                "name": name,
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
            if mcp_servers is not UNSET:
                repo_kwargs["mcp_servers"] = (
                    list(mcp_servers) if isinstance(mcp_servers, list) else []
                )
            self._repos.cron_repo.update(cron_id, **repo_kwargs)
            row = self._repos.cron_repo.get(cron_id)
            if row is None:
                raise OctopError(ErrorCode.NOT_FOUND, f"cron job {cron_id!r} not found")
            await self._unschedule(cron_id)
            if row.enabled:
                self._schedule(row)
            logger.info("CronJob %s updated", cron_id)
            return row

    async def delete(self, cron_id: str) -> None:
        async with self._lock:
            await self._unschedule(cron_id)
            self._repos.cron_repo.delete(cron_id)
            self._repos.audit_repo.write(actor=ACTOR_SYSTEM, action="cron.delete", target=cron_id)
            logger.info("CronJob %s deleted", cron_id)

    async def run_now(self, cron_id: str, *, wait: bool = False) -> None:
        """Trigger a run; embedded callers wait for bookkeeping and receive failures."""
        row = self._repos.cron_repo.get(cron_id)
        if row is None:
            raise OctopError(ErrorCode.NOT_FOUND, f"cron job {cron_id!r} not found")
        job = self._make_job(row)
        logger.info("CronJob %s triggered manually", cron_id)
        if wait:
            await job.run(raise_on_error=True)
        else:
            asyncio.ensure_future(job.run())

    def _make_job(self, row: Any) -> CronJob:
        return CronJob.from_row(
            row,
            delivery_service=self._delivery_service,
            cron_repo=self._repos.cron_repo,
            audit_repo=self._repos.audit_repo,
        )

    def _schedule(self, row: Any) -> None:
        if not row.enabled:
            return
        try:
            trigger = build_trigger(row.trigger, timezone=self._timezone)
            source = self._mail_source(row.trigger, row.user_id)
        except OctopError:
            logger.warning(
                "CronJob %s has invalid trigger %r; skipping schedule",
                row.cron_id,
                row.trigger,
            )
            return
        if isinstance(trigger, AgentlyMailTrigger):
            assert source is not None
            assert source.credential_blob is not None
            creds = decrypt_credentials(self._repos.secret_repo, source.credential_blob)

            async def on_mail(message_id: str) -> None:
                await self._run_mail_event(row.cron_id, message_id)

            self._mail_watch.subscribe(source.instance_id, row.cron_id, creds, on_mail)
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

    async def _unschedule(self, cron_id: str) -> None:
        await self._mail_watch.unsubscribe(cron_id)
        if self._scheduler.get_job(cron_id):
            self._scheduler.remove_job(cron_id)

    def _mailbox_authorized(self, source: ConnectorRow) -> bool:
        if source.credential_blob is None:
            return False
        creds = decrypt_credentials(self._repos.secret_repo, source.credential_blob)
        try:
            data = read_auth_status({**creds, "instance_id": source.instance_id})
        except (OSError, ValueError):
            return False
        return data.get("logged_in") is True and data.get("token_status") != "expired"

    def _mail_source(self, spec: str, user_id: int) -> ConnectorRow | None:
        trigger = build_trigger(spec)
        if not isinstance(trigger, AgentlyMailTrigger):
            return None
        source = self._repos.connector_repo.get(trigger.instance_id)
        if (
            source is None
            or source.kind != "agently-cli"
            or source.status != "active"
            or not source.has_credentials
        ):
            raise OctopError(ErrorCode.CRON_TRIGGER_INVALID, "Agent Mail source is unavailable")
        if source.user_id != user_id and not source.shared:
            raise OctopError(
                ErrorCode.FORBIDDEN, "Agent Mail source is not visible to the job owner"
            )
        if not self._mailbox_authorized(source):
            raise OctopError(ErrorCode.CRON_TRIGGER_INVALID, "Agent Mail mailbox is not authorized")
        return source

    async def _run_mail_event(self, cron_id: str, message_id: str) -> None:
        row = self._repos.cron_repo.get(cron_id)
        if row is None or not row.enabled:
            return
        # Recheck visibility after sharing, credentials, or the job has changed.
        source = self._mail_source(row.trigger, row.user_id)
        if source is None:
            return
        locale = resolve_user_locale(user_repo=self._repos.user_repo, user_id=row.user_id)
        prompt = (
            row.prompt
            + "\n\n"
            + tr(
                "connector.agently.new_mail_event",
                locale,
                tool=source.mcp_server_name + "_agently_read",
                message_id=message_id,
            )
        )
        event_row = replace(
            row,
            prompt=prompt,
            mcp_servers=list(dict.fromkeys([source.mcp_server_name, *row.mcp_servers])),
        )
        await self._make_job(event_row).run()

    async def reload_mail_watches(self) -> None:
        """Rebuild every mailbox watch after a full cron reload."""
        async with self._lock:
            await self._mail_watch.close()
            for row in self._repos.cron_repo.list_all(include_disabled=False):
                if row.trigger.startswith("agently:"):
                    self._schedule(row)

    async def sync_mail_watch(self, instance_id: str) -> None:
        """Start or stop watches for one mailbox without touching others."""
        async with self._lock:
            source = self._repos.connector_repo.get(instance_id)
            available = (
                source is not None
                and source.kind == "agently-cli"
                and source.status == "active"
                and source.has_credentials
                and self._mailbox_authorized(source)
            )
            if not available:
                await self._mail_watch.stop_instance(instance_id)
                return
            for row in self._repos.cron_repo.list_all(include_disabled=False):
                if row.trigger == f"agently:{instance_id}" and not self._mail_watch.has_job(
                    row.cron_id
                ):
                    self._schedule(row)

    async def stop_mail_watch(self, instance_id: str) -> None:
        await self._mail_watch.stop_instance(instance_id)

    async def resume_mail_watch(self, instance_id: str) -> None:
        await self.sync_mail_watch(instance_id)

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
            if existing.user_id != user_id:
                msg = (
                    f"session {session_key!r} belongs to user {existing.user_id!r}, not {user_id!r}"
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
        built = build_trigger(trigger, timezone=self._timezone)
        if isinstance(built, AgentlyMailTrigger):
            raise OctopError(
                ErrorCode.CRON_TRIGGER_INVALID, "system jobs cannot use Agent Mail triggers"
            )
        self._system_job_ids.add(job_id)
        self._scheduler.add_job(
            func,
            trigger=built,
            id=job_id,
            replace_existing=True,
            misfire_grace_time=300,
        )

    def unschedule_system_job(self, job_id: str) -> None:
        """Remove a process-level job previously registered via :meth:`schedule_system_job`."""
        self._system_job_ids.discard(job_id)
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

    def has_system_job(self, job_id: str) -> bool:
        """True when a system job id is currently registered with the scheduler."""
        return self._scheduler.get_job(job_id) is not None
