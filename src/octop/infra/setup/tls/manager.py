"""Orchestrate TLS preflight, ACME issuance, and config updates."""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from octop.config import OctopConfig
from octop.i18n import tr
from octop.infra.setup.tls.acme_issue import issue_certificate_http01
from octop.infra.setup.tls.listeners import TLS_HTTP_PORT, TLS_HTTPS_PORT
from octop.infra.setup.tls.modes import (
    TlsIssueMode,
    is_issue_eligible,
    tls_issue_mode,
    validate_issue_domain,
)
from octop.infra.setup.tls.preflight import PreflightResult, run_preflight
from octop.infra.setup.tls.store import install_letsencrypt_cert, resolve_tls_paths
from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)


class TlsTaskState(StrEnum):
    IDLE = "idle"
    PREFLIGHT = "preflight"
    CHALLENGING = "challenging"
    ISSUING = "issuing"
    INSTALLING = "installing"
    RESTART_REQUIRED = "restart_required"
    ACTIVE = "active"
    FAILED = "failed"


_BUSY_STATES = frozenset(
    {
        TlsTaskState.PREFLIGHT,
        TlsTaskState.CHALLENGING,
        TlsTaskState.ISSUING,
        TlsTaskState.INSTALLING,
    }
)


@dataclass
class TlsTask:
    state: TlsTaskState = TlsTaskState.IDLE
    domain: str = ""
    error: str = ""
    steps: list[str] = field(default_factory=list)
    staging: bool = False


class TlsManager:
    """In-process TLS issuance state (single wkbuddy process)."""

    def __init__(self) -> None:
        self._task = TlsTask()
        self._async_lock = asyncio.Lock()
        self._task_guard = threading.Lock()
        self._bg: asyncio.Task[None] | None = None

    def is_busy(self) -> bool:
        with self._task_guard:
            return self._task.state in _BUSY_STATES

    def _snapshot_task(self) -> TlsTask:
        with self._task_guard:
            return TlsTask(
                state=self._task.state,
                domain=self._task.domain,
                error=self._task.error,
                steps=list(self._task.steps),
                staging=self._task.staging,
            )

    def _set_task(self, **kwargs: object) -> None:
        with self._task_guard:
            for key, value in kwargs.items():
                setattr(self._task, key, value)

    def _append_step(self, step: str) -> None:
        with self._task_guard:
            self._task.steps.append(step)

    def status_payload(self, config: OctopConfig, paths: PathLayout) -> dict[str, Any]:
        tls = config.tls
        task = self._snapshot_task()
        state = self._resolve_display_state(config, paths, task)
        cert_path, key_path = resolve_tls_paths(paths.root, tls)
        mode = tls_issue_mode(config)
        dual = (
            tls.enabled
            and config.port == TLS_HTTPS_PORT
            and tls.http_port == TLS_HTTP_PORT
            and cert_path is not None
        )
        return {
            "tls": {
                "enabled": tls.enabled,
                "mode": tls.mode,
                "domains": list(tls.domains),
                "issued_at": tls.issued_at,
                "expires_at": tls.expires_at,
                "acme_staging": tls.acme_staging,
                "http_port": tls.http_port,
                "https_port": config.port if tls.enabled else None,
                "dual_listeners": dual,
                "cert_present": cert_path is not None and key_path is not None,
            },
            "task": {
                "state": state.value,
                "domain": task.domain,
                "error": task.error,
                "steps": task.steps,
                "staging": task.staging,
            },
            "eligible": is_issue_eligible(config),
            "issue_mode": mode.value if mode != TlsIssueMode.NONE else None,
            "renewal": mode == TlsIssueMode.RENEWAL,
        }

    def _resolve_display_state(
        self,
        config: OctopConfig,
        paths: PathLayout,
        task: TlsTask,
    ) -> TlsTaskState:
        if task.state in (
            TlsTaskState.PREFLIGHT,
            TlsTaskState.CHALLENGING,
            TlsTaskState.ISSUING,
            TlsTaskState.INSTALLING,
            TlsTaskState.FAILED,
        ):
            return task.state
        if task.state == TlsTaskState.RESTART_REQUIRED:
            if config.tls.enabled and config.port == TLS_HTTPS_PORT:
                cert, key = resolve_tls_paths(paths.root, config.tls)
                if cert and key:
                    return TlsTaskState.ACTIVE
            return TlsTaskState.RESTART_REQUIRED
        if config.tls.enabled and config.port == TLS_HTTPS_PORT:
            cert, key = resolve_tls_paths(paths.root, config.tls)
            if cert and key:
                return TlsTaskState.ACTIVE
        return TlsTaskState.IDLE

    async def run_preflight(
        self,
        domain: str,
        config: OctopConfig,
        *,
        locale: str = "en",
    ) -> PreflightResult:
        return await asyncio.to_thread(run_preflight, domain, config, locale=locale)

    async def start_issue(
        self,
        *,
        domain: str,
        config: OctopConfig,
        paths: PathLayout,
        staging: bool = False,
        locale: str = "en",
    ) -> PreflightResult:
        normalized = validate_issue_domain(domain, config)
        mode = tls_issue_mode(config)
        if mode == TlsIssueMode.NONE:
            msg = "TLS issuance is not eligible in current configuration"
            raise RuntimeError(msg)

        async with self._async_lock:
            if self._bg is not None and not self._bg.done():
                msg = "certificate issuance already in progress"
                raise RuntimeError(msg)

            self._set_task(
                state=TlsTaskState.PREFLIGHT,
                domain=normalized,
                staging=staging,
                error="",
                steps=[],
            )

            result = await self.run_preflight(normalized, config, locale=locale)
            if not result.ok:
                self._set_task(
                    state=TlsTaskState.FAILED,
                    error=tr("tls.preflight_failed_summary", locale),
                )
                return result

            self._set_task(state=TlsTaskState.CHALLENGING)
            self._bg = asyncio.create_task(
                self._issue_worker(
                    domain=normalized,
                    paths=paths,
                    staging=staging,
                    renewal=mode == TlsIssueMode.RENEWAL,
                )
            )
            return result

    async def _issue_worker(
        self,
        *,
        domain: str,
        paths: PathLayout,
        staging: bool,
        renewal: bool,
    ) -> None:
        try:

            def on_progress(step: str) -> None:
                self._append_step(step)
                if step == "preparing_http01_challenge":
                    self._set_task(state=TlsTaskState.CHALLENGING)
                elif step in ("answering_challenge", "waiting_for_validation"):
                    self._set_task(state=TlsTaskState.ISSUING)

            cert_pem, key_pem, expires_at = await asyncio.to_thread(
                issue_certificate_http01,
                domain=domain,
                paths=paths,
                staging=staging,
                on_progress=on_progress,
            )

            self._set_task(state=TlsTaskState.INSTALLING)
            await asyncio.to_thread(
                install_letsencrypt_cert,
                paths,
                domain=domain,
                cert_pem=cert_pem,
                key_pem=key_pem,
                expires_at=expires_at,
                acme_staging=staging,
            )
            self._set_task(state=TlsTaskState.RESTART_REQUIRED, error="")
            if renewal:
                logger.info("TLS certificate renewed for %s; restart to load new cert", domain)
        except Exception as exc:
            logger.exception("TLS issuance failed")
            self._set_task(state=TlsTaskState.FAILED, error=str(exc))


_tls_manager = TlsManager()


def get_tls_manager() -> TlsManager:
    return _tls_manager
