"""OctopServer — process-level orchestrator."""

from __future__ import annotations

import logging
import os
import time
from contextlib import suppress
from dataclasses import dataclass
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from octop.config import load_config
from octop.infra.agents.experts.catalog import ExpertCatalog, default_library_root
from octop.infra.agents.manager import AgentManager
from octop.infra.agents.plugins.manager import PluginManager
from octop.infra.agents.subagents.catalog import SubagentCatalog, default_package_root
from octop.infra.cron.manager import CronManager
from octop.infra.db.factory import open_database
from octop.infra.db.migrate import run_migrations
from octop.infra.db.services import SharedServices, build_shared_services
from octop.infra.gateway.gateway import Gateway
from octop.infra.proactive.scheduler import ProactiveCareScheduler
from octop.infra.proactive.service import ProactiveCareService
from octop.infra.setup import password_file as _wizard_pw
from octop.infra.setup.password_file import WIZARD_FILE_NAME
from octop.infra.setup.wizard_tokens import WizardTokenStore
from octop.infra.users.manager import UserManager
from octop.infra.utils.paths import PathLayout

logger = logging.getLogger(__name__)


def _build_log_handler(log_path: Path, retention_days: int) -> TimedRotatingFileHandler:
    """Create a daily-rotating file handler that also enforces retention."""
    handler = TimedRotatingFileHandler(
        log_path,
        when="midnight",
        interval=1,
        backupCount=retention_days,
        encoding="utf-8",
    )
    # Rotated files get a date suffix, e.g. octop.log.2026-07-16
    handler.suffix = "%Y-%m-%d"
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(name)s — %(message)s"))
    return handler


def _purge_stale_logs(log_dir: Path, retention_days: int) -> None:
    """Delete rotated octop log files older than ``retention_days`` (mtime based).

    ``TimedRotatingFileHandler`` only trims by count at rollover time, so a service
    that is offline for a long stretch can accumulate stale files. This purges them
    on startup as a safety net.
    """
    if retention_days <= 0:
        return
    cutoff = time.time() - retention_days * 86400
    for entry in log_dir.glob("octop.log.*"):
        if entry.is_file() and entry.stat().st_mtime < cutoff:
            with suppress(OSError):
                entry.unlink()


def _attach_log_handler(target: logging.Logger, handler: TimedRotatingFileHandler) -> None:
    """Add ``handler`` to ``target`` only if an equivalent one is not present yet."""
    if not any(
        isinstance(h, TimedRotatingFileHandler) and h.baseFilename == handler.baseFilename
        for h in target.handlers
    ):
        target.addHandler(handler)


@dataclass
class AppRuntime:
    """Live singletons — constructed after boot."""

    agent_registry: AgentManager
    gateway: Gateway
    cron_manager: CronManager
    user_manager: UserManager
    proactive_scheduler: ProactiveCareScheduler


class OctopServer:
    def __init__(self, home: Path | None = None) -> None:
        self._home = home or PathLayout.from_env().root
        self.paths = PathLayout(self._home)
        self.services: SharedServices | None = None
        self.app_runtime: AppRuntime | None = None
        self.expert_catalog: ExpertCatalog | None = None
        self.subagent_catalog: SubagentCatalog | None = None
        self.plugin_manager: PluginManager | None = None
        self.wizard_tokens = WizardTokenStore(ttl_seconds=300)
        self._started = False
        self._started_at: int | None = None

    # Backward compat: expose user_manager directly
    @property
    def user_manager(self) -> UserManager | None:
        return self.app_runtime.user_manager if self.app_runtime else None

    async def start(self) -> None:
        if self._started:
            return
        self.paths.ensure_root()
        from octop.infra.utils.env_file import apply_env_file, env_file_path  # noqa: PLC0415

        apply_env_file(env_file_path(self.paths.root))
        self._setup_logging()
        config = load_config(self.paths.config)
        db = open_database(config, self.paths)
        run_migrations(db)
        self.services = build_shared_services(db=db, paths=self.paths, config=config)
        self._ensure_jwt_secret()
        self.expert_catalog = ExpertCatalog(default_library_root())
        self.expert_catalog.refresh()
        self.subagent_catalog = SubagentCatalog(default_package_root())
        self.subagent_catalog.refresh()

        self.plugin_manager = PluginManager(
            plugins_dir=self.paths.plugins_dir,
            config_path=self.paths.config,
        )
        self.plugin_manager.load_installed(install_deps=True)

        # Boot global singletons in dependency order
        registry = AgentManager(
            repos=self.services.repos,
            paths=self.paths,
            config=config,
            expert_catalog=self.expert_catalog,
            plugin_manager=self.plugin_manager,
        )

        gateway = Gateway(
            agent_manager=registry,
            repos=self.services.repos,
        )
        await gateway.boot()

        import time  # noqa: PLC0415

        from octop import __version__  # noqa: PLC0415

        started_at = int(time.time())
        gateway.set_slash_meta(version=__version__, started_at=started_at)
        self._started_at = started_at

        cron_mgr = CronManager(
            gateway=gateway,
            repos=self.services.repos,
            timezone=config.cron_timezone,
        )
        await cron_mgr.boot()

        from octop.infra.setup.tls.renewal import install_auto_renewal_job

        install_auto_renewal_job(cron_mgr, paths=self.paths)

        registry.set_cron_manager(cron_mgr)

        registry.set_team_processor(gateway.processor)

        # Build the proactive care push service and scheduler
        care_service = ProactiveCareService(
            gateway=gateway,
            care_push_repo=self.services.repos.care_push_repo,
            agent_manager=registry,
        )
        proactive_scheduler = ProactiveCareScheduler(
            care_service=care_service,
            config_repo=self.services.repos.proactive_care_config_repo,
            session_repo=self.services.repos.session_repo,
        )

        await registry.boot()
        await gateway.refresh_media_backends()

        user_mgr = UserManager(self.services)
        await user_mgr.boot()

        # Start the proactive care scheduler (after registry.boot(), ensuring agents are loaded)
        await proactive_scheduler.start_all()

        self.app_runtime = AppRuntime(
            agent_registry=registry,
            gateway=gateway,
            cron_manager=cron_mgr,
            user_manager=user_mgr,
            proactive_scheduler=proactive_scheduler,
        )
        self._started = True
        wizard_home = Path.home()
        if config.require_setup_password:
            try:
                new_pw = _wizard_pw.boot_self_heal(wizard_home, user_count=user_mgr.count())
            except OSError as err:
                logger.warning("wizard self-heal failed: %s", err)
                new_pw = None
        else:
            if user_mgr.count() == 0:
                _wizard_pw.remove_password(wizard_home)
            new_pw = None
        if new_pw is not None:
            banner = (
                "\n\033[33m"
                "╔══════════════════════════════════════════════════════════╗\n"
                "║  Octop first-run wizard password (one-time use):          ║\n"
                f"║  {new_pw:<54}  ║\n"
                "║  Open the dashboard and paste it into the setup wizard.  ║\n"
                "║  File: ~/octop-login.txt                                   ║\n"
                "╚══════════════════════════════════════════════════════════╝"
                "\033[0m\n"
            )
            print(banner, flush=True)
            logger.info(
                "wizard password generated; file=%s",
                wizard_home / WIZARD_FILE_NAME,
            )

    async def stop(self) -> None:
        if not self._started or self.app_runtime is None:
            return
        rt = self.app_runtime
        try:
            await rt.proactive_scheduler.shutdown()
            await rt.cron_manager.shutdown()
            await rt.gateway.shutdown()
            await rt.agent_registry.shutdown()
            await rt.user_manager.shutdown_all()
        finally:
            if self.services is not None:
                self.services.db.close()
            self._started = False
            logger.info("octop server stopped")

    # ----- helpers -----

    def _setup_logging(self) -> None:
        log_dir = self.paths.logs_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.paths.log

        # Migrate the legacy single-file log (~/.octop/octop.log) into the new logs dir.
        legacy = self.paths.root / "octop.log"
        if legacy.exists() and not log_path.exists():
            with suppress(OSError):
                legacy.replace(log_path)

        raw_retention = os.environ.get("OCTOP_LOG_RETENTION_DAYS", "14") or "14"
        try:
            retention_days = int(raw_retention)
        except ValueError:
            retention_days = 14
        handler = _build_log_handler(log_path, retention_days)
        _purge_stale_logs(log_dir, retention_days)

        root = logging.getLogger()
        _attach_log_handler(root, handler)
        # Persist framework (uvicorn) request/error logs into the same file too.
        for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
            _attach_log_handler(logging.getLogger(name), handler)

        level = os.environ.get("OCTOP_LOG_LEVEL", "info").upper()
        root.setLevel(getattr(logging, level, logging.INFO))

    def _ensure_jwt_secret(self) -> None:
        assert self.services is not None
        self.services.secret_repo.get_or_create("jwt", lambda: os.urandom(32))
