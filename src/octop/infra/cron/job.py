"""CronJob — APScheduler callable with status and audit bookkeeping."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar

from octop.infra.cron.delivery import CronDeliveryCommand
from octop.infra.cron.task_type import normalize_cron_task_type
from octop.infra.db.repos.audit import ACTOR_SYSTEM

if TYPE_CHECKING:
    from octop.infra.cron.delivery import CronDeliveryService
    from octop.infra.db.repos.audit import AuditRepo
    from octop.infra.db.repos.cron import CronJobRepo, CronJobRow

logger = logging.getLogger(__name__)


class CronJob:
    """APScheduler callable with status and audit bookkeeping.

    Executions are serialized per cron id across instances (scheduled runs and
    manual ``run-now`` share the slot): an overlapping trigger is recorded as
    ``skipped_overlap`` instead of being dropped silently (#1014).
    """

    _in_flight: ClassVar[set[str]] = set()

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
        on_budget_exceeded: Callable[[str], None] | None = None,
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
        self._on_budget_exceeded = on_budget_exceeded

    @classmethod
    def from_row(
        cls,
        row: CronJobRow,
        *,
        delivery_service: CronDeliveryService,
        cron_repo: CronJobRepo,
        audit_repo: AuditRepo,
        on_budget_exceeded: Callable[[str], None] | None = None,
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
            on_budget_exceeded=on_budget_exceeded,
        )

    async def run(self, *, raise_on_error: bool = False) -> None:
        from octop.infra.metrics import METRICS  # noqa: PLC0415

        if self._cron_id in CronJob._in_flight:
            METRICS.inc("cron_skipped_overlap_total")
            self._cron_repo.set_run_status(
                self._cron_id,
                ts=int(time.time()),
                status="skipped_overlap",
                error="previous run still in progress",
            )
            self._audit_repo.write(
                actor=ACTOR_SYSTEM,
                action="cron.run_skipped_overlap",
                target=self._cron_id,
            )
            logger.warning(
                "CronJob %s skipped: previous run still in progress "
                "(runtime exceeds the schedule interval)",
                self._cron_id,
            )
            return
        CronJob._in_flight.add(self._cron_id)
        try:
            await self._run_exclusive(raise_on_error=raise_on_error)
        finally:
            CronJob._in_flight.discard(self._cron_id)

    async def _run_exclusive(self, *, raise_on_error: bool) -> None:
        from octop.infra.metrics import METRICS  # noqa: PLC0415

        METRICS.inc("cron_runs_total")
        ts = int(time.time())

        try:
            run_tokens = await self._delivery_service.deliver(
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
            self._cron_repo.set_run_status(self._cron_id, ts=ts, status="error", error=err)
            self._audit_repo.write(
                actor=ACTOR_SYSTEM,
                action="cron.run_failed",
                target=self._cron_id,
                payload=err,
            )
            if raise_on_error:
                raise
            return
        self._cron_repo.set_run_status(self._cron_id, ts=ts, status="ok", error=None)
        self._audit_repo.write(
            actor=ACTOR_SYSTEM,
            action="cron.run_ok",
            target=self._cron_id,
        )
        if run_tokens and self._cron_repo.apply_token_budget(self._cron_id, run_tokens=run_tokens):
            METRICS.inc("cron_budget_exceeded_total")
            self._cron_repo.set_run_status(
                self._cron_id,
                ts=ts,
                status="budget_exceeded",
                error="24h token budget exceeded; job disabled",
            )
            self._audit_repo.write(
                actor=ACTOR_SYSTEM,
                action="cron.budget_exceeded",
                target=self._cron_id,
                payload=f"run={run_tokens} tokens; budget window exceeded",
            )
            logger.warning(
                "CronJob %s disabled: 24h token budget exceeded (last run %d tokens)",
                self._cron_id,
                run_tokens,
            )
            if self._on_budget_exceeded is not None:
                self._on_budget_exceeded(self._cron_id)
