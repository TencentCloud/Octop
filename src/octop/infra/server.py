"""OctopServer — process-level orchestrator."""

from __future__ import annotations

import gzip
import logging
import os
import shutil
import time
from contextlib import suppress
from dataclasses import dataclass
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

from octop.config import OctopConfig, load_config
from octop.infra.agents.experts.catalog import ExpertCatalog, default_library_root
from octop.infra.agents.manager import AgentManager
from octop.infra.agents.plugins.manager import PluginManager
from octop.infra.agents.subagents.catalog import SubagentCatalog, default_package_root
from octop.infra.cron.manager import CronManager
from octop.infra.db.factory import open_database, should_defer_control_plane_db
from octop.infra.db.migrate import run_migrations
from octop.infra.db.services import SharedServices, build_shared_services
from octop.infra.gateway.gateway import Gateway
from octop.infra.mobile.config_probe import ensure_mobile_capabilities_probed
from octop.infra.proactive.scheduler import ProactiveCareScheduler
from octop.infra.proactive.service import ProactiveCareService
from octop.infra.setup import password_file as _wizard_pw
from octop.infra.setup.password_file import WIZARD_FILE_NAME
from octop.infra.setup.wizard_tokens import WizardTokenStore
from octop.infra.users.manager import UserManager
from octop.infra.utils.paths import PathLayout

if TYPE_CHECKING:
    from octop.infra.auth.sso.service import SsoService
    from octop.infra.trajectory.service import TrajectoryService

logger = logging.getLogger(__name__)

# Default 100 MiB per active log file before size-triggered rollover (in addition to daily).
DEFAULT_LOG_MAX_BYTES = 100 * 1024 * 1024
DEFAULT_LOG_RETENTION_DAYS = 14


class SizeTimedRotatingFileHandler(TimedRotatingFileHandler):
    """Daily rotation with an optional per-file byte cap (whichever triggers first)."""

    def __init__(
        self,
        filename: str | os.PathLike[str],
        *,
        max_bytes: int = 0,
        compress_rotated: bool = True,
        **kwargs: object,
    ) -> None:
        super().__init__(filename, **kwargs)  # type: ignore[arg-type]
        self.max_bytes = max(0, max_bytes)
        self.compress_rotated = compress_rotated

    def shouldRollover(self, record: logging.LogRecord) -> bool:
        if super().shouldRollover(record):
            return True
        if self.max_bytes <= 0:
            return False
        if self.stream is None:
            self.stream = self._open()
        self.stream.flush()
        return self.stream.tell() >= self.max_bytes

    def rotate(self, source: str, dest: str) -> None:
        super().rotate(source, dest)
        if self.compress_rotated:
            # logrotate delaycompress: leave this cycle's dest plain; gzip prior plains.
            delaycompress_rotated_logs(Path(dest).parent, enabled=True, keep=Path(dest))

    def rotation_filename(self, default_name: str) -> str:
        """Avoid overwriting an existing daily backup when size rolls twice same day."""
        if not os.path.exists(default_name) and not os.path.exists(f"{default_name}.gz"):
            return default_name
        index = 1
        while True:
            candidate = f"{default_name}-{index:03d}"
            if not os.path.exists(candidate) and not os.path.exists(f"{candidate}.gz"):
                return candidate
            index += 1


def gzip_rotated_log(path: Path) -> None:
    """Compress a rotated log file to ``{name}.gz`` and remove the plain file."""
    if not path.is_file() or path.suffix == ".gz":
        return
    gz_path = path.with_name(f"{path.name}.gz")
    if gz_path.exists():
        return
    try:
        with path.open("rb") as src, gzip.open(gz_path, "wb", compresslevel=6) as dst:
            shutil.copyfileobj(src, dst)
        path.unlink()
    except OSError:
        with suppress(OSError):
            if gz_path.exists():
                gz_path.unlink()


def _parse_log_compress() -> bool:
    raw = (os.environ.get("OCTOP_LOG_COMPRESS", "1") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def delaycompress_rotated_logs(
    log_dir: Path,
    *,
    enabled: bool,
    keep: Path | None = None,
) -> None:
    """Gzip older rotated plains; leave ``keep`` (or the newest) uncompressed.

    Matches logrotate ``compress`` + ``delaycompress``: postpone compression of the
    previous log file until the next rotation cycle
    (https://github.com/logrotate/logrotate).
    """
    if not enabled or not log_dir.is_dir():
        return
    plains = [
        entry
        for entry in log_dir.glob("octop.log.*")
        if entry.is_file() and not entry.name.endswith(".gz")
    ]
    if not plains:
        return
    keep_path = max(plains, key=lambda p: p.stat().st_mtime) if keep is None else keep
    keep_resolved = keep_path.resolve()
    for entry in plains:
        if entry.resolve() == keep_resolved:
            continue
        gzip_rotated_log(entry)


def _parse_log_retention_days() -> int:
    raw = os.environ.get("OCTOP_LOG_RETENTION_DAYS", str(DEFAULT_LOG_RETENTION_DAYS)) or str(
        DEFAULT_LOG_RETENTION_DAYS
    )
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_LOG_RETENTION_DAYS


def _parse_log_max_bytes() -> int:
    raw = os.environ.get("OCTOP_LOG_MAX_BYTES", str(DEFAULT_LOG_MAX_BYTES)) or str(
        DEFAULT_LOG_MAX_BYTES
    )
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_LOG_MAX_BYTES


def _build_log_handler(
    log_path: Path,
    retention_days: int,
    *,
    max_bytes: int = DEFAULT_LOG_MAX_BYTES,
    compress_rotated: bool = True,
) -> SizeTimedRotatingFileHandler:
    """Create a daily + size-capped rotating file handler with retention."""
    handler = SizeTimedRotatingFileHandler(
        log_path,
        when="midnight",
        interval=1,
        backupCount=retention_days,
        encoding="utf-8",
        max_bytes=max_bytes,
        compress_rotated=compress_rotated,
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
    trajectory_service: TrajectoryService | None = None

    def replace_services(self, services: SharedServices, config: OctopConfig) -> None:
        """Retarget all runtime singletons onto a new SharedServices / config.

        Used when the setup wizard hot-swaps the control-plane DB while empty.
        """
        self.user_manager.replace_services(services)
        self.agent_registry.replace_persistence(services.repos, config)
        self.gateway.replace_repos(services.repos)
        self.cron_manager.replace_repos(services.repos)
        self.proactive_scheduler.replace_persistence(
            config_repo=services.repos.proactive_care_config_repo,
            session_repo=services.repos.session_repo,
            care_push_repo=services.repos.care_push_repo,
        )
        if self.trajectory_service is not None:
            from octop.infra.trajectory.store import TrajectoryStore  # noqa: PLC0415

            self.trajectory_service.replace_store(TrajectoryStore(services.trajectory_event_repo))


class OctopServer:
    def __init__(self, home: Path | None = None) -> None:
        self._home = home or PathLayout.from_env().root
        self.paths = PathLayout(self._home)
        self.config: OctopConfig | None = None
        self.services: SharedServices | None = None
        self.app_runtime: AppRuntime | None = None
        self.expert_catalog: ExpertCatalog | None = None
        self.subagent_catalog: SubagentCatalog | None = None
        self.plugin_manager: PluginManager | None = None
        self.wizard_tokens = WizardTokenStore(ttl_seconds=300)
        self._started = False
        self._started_at: int | None = None
        self._sso_service: SsoService | None = None

    # Backward compat: expose user_manager directly
    @property
    def user_manager(self) -> UserManager | None:
        return self.app_runtime.user_manager if self.app_runtime else None

    @property
    def sso_service(self) -> SsoService:
        """Process-level SSO service so discovery/JWKS cache survives across requests."""
        from octop.infra.auth.sso.service import SsoService as SsoServiceCls  # noqa: PLC0415

        if self.services is None or self.user_manager is None:
            raise RuntimeError("SSO service requires a started server with user manager")
        if (
            self._sso_service is None
            or getattr(self._sso_service, "_services", None) is not self.services
            or getattr(self._sso_service, "_user_manager", None) is not self.user_manager
        ):
            self._sso_service = SsoServiceCls(self.services, self.user_manager)
        return self._sso_service

    @property
    def database_bound(self) -> bool:
        return self.services is not None and self.app_runtime is not None

    async def start(self) -> None:
        if self._started:
            return
        self.paths.ensure_root()
        # fnOS/容器内非 root 用户场景：把用户级 npm 全局 bin 目录（~/.npm-global）
        # 纳入进程 PATH，保证连接器 CLI（wecom-cli / lark-cli）可被检测与调用。
        from octop.infra.connectors.gateway.cli_install import ensure_cli_path  # noqa: PLC0415

        ensure_cli_path()
        from octop.infra.utils.env_file import apply_env_file, env_file_path  # noqa: PLC0415

        apply_env_file(env_file_path(self.paths.root))
        self._setup_logging()
        config = ensure_mobile_capabilities_probed(self.paths.config)
        self.config = config

        self.expert_catalog = ExpertCatalog(
            default_library_root(),
            extra_roots=[self.paths.expert_market_dir],
        )
        self.expert_catalog.refresh()
        self.subagent_catalog = SubagentCatalog(default_package_root())
        self.subagent_catalog.refresh()

        self.plugin_manager = PluginManager(
            plugins_dir=self.paths.plugins_dir,
            config_path=self.paths.config,
        )
        self.plugin_manager.seed_bundled()
        self.plugin_manager.load_installed(install_deps=True)

        import time  # noqa: PLC0415

        self._started_at = int(time.time())

        if should_defer_control_plane_db(config, self.paths):
            self._started = True
            self._emit_wizard_password(user_count=0)
            logger.info("control-plane database deferred until setup wizard chooses a backend")
            return

        db = open_database(config, self.paths)
        run_migrations(db)
        self.services = build_shared_services(db=db, paths=self.paths, config=config)
        self._ensure_jwt_secret()
        await self._boot_runtime(config)
        self._started = True
        assert self.user_manager is not None
        self._emit_wizard_password(user_count=self.user_manager.count())

    async def bind_control_plane(self) -> None:
        """Open the configured control-plane DB and boot runtime (first-run wizard).

        Idempotent when already bound: no-op. Call after persisting ``database``
        into ``config.json``. Does not rebind an existing live pool — use
        ``rebind_control_plane`` only when swapping while ``user_count == 0``.
        """
        if self.database_bound:
            return
        config = load_config(self.paths.config)
        self.config = config
        db = open_database(config, self.paths)
        try:
            run_migrations(db)
        except Exception:
            db.close()
            raise
        self.services = build_shared_services(db=db, paths=self.paths, config=config)
        self._ensure_jwt_secret()
        await self._boot_runtime(config)
        logger.info(
            "control-plane database bound driver=%s",
            config.database.driver,
        )

    async def _boot_runtime(self, config: OctopConfig) -> None:
        assert self.services is not None
        assert self.expert_catalog is not None
        assert self.plugin_manager is not None

        from octop.infra.utils.browser_media import (  # noqa: PLC0415
            configure_browser_idle_timeout,
        )

        configure_browser_idle_timeout(config.browser_idle_timeout_minutes)

        registry = AgentManager(
            repos=self.services.repos,
            paths=self.paths,
            config=config,
            expert_catalog=self.expert_catalog,
            plugin_manager=self.plugin_manager,
        )

        from octop.infra.trajectory.live import TrajectoryLiveBus  # noqa: PLC0415
        from octop.infra.trajectory.service import TrajectoryService  # noqa: PLC0415
        from octop.infra.trajectory.store import TrajectoryStore  # noqa: PLC0415

        trajectory_service = TrajectoryService(
            TrajectoryStore(self.services.trajectory_event_repo),
            TrajectoryLiveBus(),
        )

        gateway = Gateway(
            agent_manager=registry,
            repos=self.services.repos,
            trajectory_service=trajectory_service,
        )
        await gateway.boot()

        from octop import __version__  # noqa: PLC0415

        started_at = self._started_at
        if started_at is None:
            import time  # noqa: PLC0415

            started_at = int(time.time())
        gateway.set_slash_meta(version=__version__, started_at=started_at)
        self._started_at = started_at

        from octop.infra.cron.delivery import CronDeliveryService  # noqa: PLC0415

        cron_delivery = CronDeliveryService(
            gateway=gateway,
            agent_manager=registry,
            repos=self.services.repos,
        )
        cron_mgr = CronManager(
            gateway=gateway,
            delivery_service=cron_delivery,
            repos=self.services.repos,
            timezone=config.default_timezone,
        )
        await cron_mgr.boot()

        from octop.infra.setup.tls.renewal import install_auto_renewal_job

        install_auto_renewal_job(cron_mgr, paths=self.paths)

        from octop.infra.backup.auto import install_auto_backup_job

        install_auto_backup_job(cron_mgr, server=self)

        registry.set_cron_manager(cron_mgr)
        registry.set_team_processor(gateway.processor)

        care_service = ProactiveCareService(
            gateway=gateway,
            care_push_repo=self.services.repos.care_push_repo,
            agent_manager=registry,
            timezone=config.default_timezone,
        )
        proactive_scheduler = ProactiveCareScheduler(
            care_service=care_service,
            config_repo=self.services.repos.proactive_care_config_repo,
            session_repo=self.services.repos.session_repo,
        )
        registry.set_proactive_scheduler(proactive_scheduler)

        await registry.boot()
        await gateway.refresh_media_backends()

        user_mgr = UserManager(self.services)
        await user_mgr.boot()
        await proactive_scheduler.start_all()

        self.app_runtime = AppRuntime(
            agent_registry=registry,
            gateway=gateway,
            cron_manager=cron_mgr,
            user_manager=user_mgr,
            proactive_scheduler=proactive_scheduler,
            trajectory_service=trajectory_service,
        )
        from octop.infra.knowledge.jobs import resume_pending_index_jobs  # noqa: PLC0415

        resume_pending_index_jobs(self.services)

    def _emit_wizard_password(self, *, user_count: int) -> None:
        config = self.config
        if config is None:
            return
        wizard_home = Path.home()
        if config.require_setup_password:
            try:
                new_pw = _wizard_pw.boot_self_heal(wizard_home, user_count=user_count)
            except OSError as err:
                logger.warning("wizard self-heal failed: %s", err)
                new_pw = None
        else:
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
        if not self._started:
            return
        try:
            if self.app_runtime is not None:
                rt = self.app_runtime
                await rt.proactive_scheduler.shutdown()
                await rt.cron_manager.shutdown()
                await rt.gateway.shutdown()
                await rt.agent_registry.shutdown()
                await rt.user_manager.shutdown_all()
        finally:
            if self.services is not None:
                self.services.db.close()
            self.services = None
            self.app_runtime = None
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

        retention_days = _parse_log_retention_days()
        max_bytes = _parse_log_max_bytes()
        compress_rotated = _parse_log_compress()
        handler = _build_log_handler(
            log_path,
            retention_days,
            max_bytes=max_bytes,
            compress_rotated=compress_rotated,
        )
        _purge_stale_logs(log_dir, retention_days)
        # Catch up: gzip older plains, leave the newest rotated file plain (delaycompress).
        delaycompress_rotated_logs(log_dir, enabled=compress_rotated)

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
