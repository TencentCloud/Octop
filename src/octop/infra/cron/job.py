"""CronJob — APScheduler callable with status and audit bookkeeping."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from octop.infra.cron.delivery import CronDeliveryCommand
from octop.infra.cron.task_type import normalize_cron_task_type
from octop.infra.db.repos.audit import ACTOR_SYSTEM
from octop.infra.errors import ErrorCode, OctopError

if TYPE_CHECKING:
    from octop.infra.cron.delivery import CronDeliveryService
    from octop.infra.db.repos.audit import AuditRepo
    from octop.infra.db.repos.cron import CronJobRepo, CronJobRow

logger = logging.getLogger(__name__)


class CronJob:
    def __init__(
        self,
        *,
        cron_id: str,
        name: str,
        agent_id: str,
        prompt: str,
        fresh_thread: bool,
        session_key: str,
        model: str | None,
        task_type: str,
        mcp_servers: list[str] | None,
        user_id: int,
        delivery_service: CronDeliveryService,
        cron_repo: CronJobRepo,
        audit_repo: AuditRepo,
    ) -> None:
        self._cron_id = cron_id
        self._name = name
        self._agent_id = agent_id
        self._prompt = prompt
        self._fresh_thread = fresh_thread
        self._session_key = session_key
        self._model = model
        self._task_type = normalize_cron_task_type(task_type)
        self._mcp_servers = list(mcp_servers or [])
        self._user_id = user_id
        self._delivery_service = delivery_service
        self._cron_repo = cron_repo
        self._audit_repo = audit_repo

    @classmethod
    def from_row(
        cls,
        row: CronJobRow,
        *,
        delivery_service: CronDeliveryService,
        cron_repo: CronJobRepo,
        audit_repo: AuditRepo,
    ) -> CronJob:
        return cls(
            cron_id=row.cron_id,
            name=row.name,
            agent_id=row.agent_id,
            prompt=row.prompt,
            fresh_thread=bool(row.fresh_thread),
            session_key=row.session_key,
            model=row.model,
            task_type=row.task_type,
            mcp_servers=list(row.mcp_servers),
            user_id=row.user_id,
            delivery_service=delivery_service,
            cron_repo=cron_repo,
            audit_repo=audit_repo,
        )

    async def run(
        self,
        *,
        raise_on_error: bool = False,
        lease_token: str | None = None,
        disable_after: bool = False,
    ) -> bool:
        """Run the delivery. Return False when ``lease_token`` was lost before recording."""
        from octop.infra.metrics import METRICS  # noqa: PLC0415

        METRICS.inc("cron_runs_total")
        ts = int(time.time())

        try:
            await self._delivery_service.deliver(
                CronDeliveryCommand(
                    cron_id=self._cron_id,
                    cron_name=self._name,
                    agent_id=self._agent_id,
                    user_id=self._user_id,
                    session_key=self._session_key,
                    prompt=self._prompt,
                    fresh_thread=self._fresh_thread,
                    task_type=self._task_type,
                    model=self._model,
                    mcp_servers=tuple(self._mcp_servers),
                )
            )
        except Exception as exc:
            METRICS.inc("cron_errors_total")
            logger.exception("cron job %s failed", self._cron_id)
            err = str(exc)
            recorded = self._record(
                ts,
                "error",
                err,
                lease_token=lease_token,
                disable_after=disable_after,
            )
            if not recorded:
                self._lost(raise_on_error=raise_on_error)
                return False
            self._audit_repo.write(
                actor=ACTOR_SYSTEM,
                action="cron.run_failed",
                target=self._cron_id,
                payload=err,
            )
            if raise_on_error:
                raise
            return True
        recorded_ok = self._record(
            ts,
            "ok",
            None,
            lease_token=lease_token,
            disable_after=disable_after,
        )
        if not recorded_ok:
            self._lost(raise_on_error=raise_on_error)
            return False
        self._audit_repo.write(
            actor=ACTOR_SYSTEM,
            action="cron.run_ok",
            target=self._cron_id,
        )
        return True

    def _record(
        self,
        ts: int,
        status: str,
        error: str | None,
        *,
        lease_token: str | None,
        disable_after: bool,
    ) -> bool:
        if lease_token is None:
            self._cron_repo.set_run_status(self._cron_id, ts=ts, status=status, error=error)
            if disable_after:
                self._cron_repo.update(self._cron_id, enabled=False)
            return True
        return self._cron_repo.finish_run(
            self._cron_id,
            token=lease_token,
            ts=ts,
            status=status,
            error=error,
            disable=disable_after,
        )

    def _lost(self, *, raise_on_error: bool) -> None:
        logger.warning("cron job %s lost its run lease before recording the result", self._cron_id)
        if raise_on_error:
            raise OctopError(
                ErrorCode.CRON_ALREADY_RUNNING,
                f"cron job {self._cron_id!r} lost its run lease",
            )
