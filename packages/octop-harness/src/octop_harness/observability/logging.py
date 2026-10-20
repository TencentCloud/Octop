"""Process-wide logging configuration for octop-harness.

Runtime diagnostic logs are an **application** concern, not per-agent
config. Host apps call :func:`setup_logging` once (or pass ``log_dir`` to
:class:`~octop_harness.manager.HarnessAgentManager`) so every agent in the
process writes to one set of date-named files. Direct
:class:`~octop_harness.agent.HarnessAgent` construction falls back to
:func:`ensure_logging` with the library default ``~/.octop-harness/logs``.

Standalone use writes date-named files (``YYYY-MM-DD.log``) under
``~/.octop-harness/logs``. When a single day's file exceeds ``max_bytes``,
it is size-rotated to ``YYYY-MM-DD.1.log``, ``YYYY-MM-DD.2.log``, etc.
Host apps that already own a log file (Octop's ``octop.log``) call
:func:`use_host_logging` so records propagate to the host handler instead
of opening a second file.

Each line is tagged with ``[agent=<id>]`` via :func:`logging_scope`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Literal

_HANDLER_NAME = "octop_harness_file_handler"

_log_agent_id: ContextVar[str | None] = ContextVar("octop_harness_log_agent_id", default=None)


class _LoggingState:
    """Process-wide switch: host logger owns output, so no package log file."""

    host: bool = False


_logging_state = _LoggingState()

DEFAULT_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s [agent=%(agent)s]: %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_LOG_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_LOG_BACKUP_COUNT = 5

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


def default_log_dir() -> Path:
    """Return the library default runtime log directory (``~/.octop-harness/logs``)."""
    return Path.home() / ".octop-harness" / "logs"


def resolve_log_dir(log_dir: str | Path | None = None) -> Path:
    """Resolve a host ``log_dir`` against the library default.

    ``None`` → ``~/.octop-harness/logs``. Relative paths are anchored to
    that default so ``"nested"`` becomes ``~/.octop-harness/logs/nested``.
    """
    base = default_log_dir()
    if log_dir is None:
        return base.resolve()
    path = Path(log_dir).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _today_log_filename() -> str:
    """Return the log filename for today: ``YYYY-MM-DD.log``."""
    return datetime.now().astimezone().strftime("%Y-%m-%d") + ".log"


class _AgentIdFilter(logging.Filter):
    """Stamp ``record.agent`` from the active :func:`logging_scope` ContextVar."""

    def filter(self, record: logging.LogRecord) -> bool:
        agent = _log_agent_id.get()
        record.agent = agent if agent else "-"
        return True


@contextmanager
def logging_scope(agent_id: str | None) -> Iterator[None]:
    """Tag ``octop_harness`` log records with *agent_id* for the duration."""
    token = _log_agent_id.set(agent_id if agent_id else None)
    try:
        yield
    finally:
        _log_agent_id.reset(token)


def current_log_agent_id() -> str | None:
    """Return the agent id installed by :func:`logging_scope`, if any."""
    return _log_agent_id.get()


def _existing_handler_file() -> Path | None:
    pkg_logger = logging.getLogger("octop_harness")
    for handler in pkg_logger.handlers:
        if getattr(handler, "name", None) == _HANDLER_NAME:
            raw = getattr(handler, "baseFilename", "")
            return Path(raw) if raw else None
    return None


def use_host_logging() -> None:
    """Do not open a package log file; let records propagate to the host logger.

    ``ensure_logging`` will not fall back to ``~/.octop-harness/logs`` after
    this. Any package file handler already installed is removed.
    """
    _logging_state.host = True
    pkg_logger = logging.getLogger("octop_harness")
    for handler in list(pkg_logger.handlers):
        if getattr(handler, "name", None) == _HANDLER_NAME:
            handler.close()
            pkg_logger.removeHandler(handler)
    pkg_logger.setLevel(logging.NOTSET)
    pkg_logger.propagate = True


def setup_logging(
    log_dir: str | Path,
    *,
    level: LogLevel | None = None,
    debug: bool = False,
    max_bytes: int = DEFAULT_LOG_MAX_BYTES,
    backup_count: int = DEFAULT_LOG_BACKUP_COUNT,
    log_format: str = DEFAULT_LOG_FORMAT,
    date_format: str = DEFAULT_DATE_FORMAT,
) -> Path:
    """Configure file-based logging for the ``octop_harness`` package.

    At most one package file handler is kept. A later call with the same
    date file updates the level; a call with a different path replaces the
    previous handler (host apps use one shared ``log_dir``).
    """
    _logging_state.host = False

    if level is not None:
        effective_level = getattr(logging, level, logging.INFO)
    else:
        effective_level = logging.DEBUG if debug else logging.INFO

    log_dir = Path(log_dir).expanduser().resolve()
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / _today_log_filename()

    pkg_logger = logging.getLogger("octop_harness")

    for handler in list(pkg_logger.handlers):
        if getattr(handler, "name", None) != _HANDLER_NAME:
            continue
        current_file = Path(getattr(handler, "baseFilename", ""))
        if current_file.resolve() == log_file.resolve():
            handler.setLevel(effective_level)
            pkg_logger.setLevel(effective_level)
            return log_file
        handler.close()
        pkg_logger.removeHandler(handler)

    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.name = _HANDLER_NAME
    file_handler.setLevel(effective_level)
    file_handler.addFilter(_AgentIdFilter())

    formatter = logging.Formatter(fmt=log_format, datefmt=date_format)
    file_handler.setFormatter(formatter)

    pkg_logger.addHandler(file_handler)
    pkg_logger.setLevel(effective_level)

    return log_file


def ensure_logging(
    log_dir: str | Path | None = None,
    *,
    level: LogLevel | None = None,
    debug: bool = False,
    max_bytes: int = DEFAULT_LOG_MAX_BYTES,
    backup_count: int = DEFAULT_LOG_BACKUP_COUNT,
) -> Path | None:
    """Install library-default logging only if no package file handler exists.

    Returns ``None`` when :func:`use_host_logging` is active.

    Host apps / :class:`~octop_harness.manager.HarnessAgentManager` call
    :func:`setup_logging` once. Direct agent construction uses this so
    defaults still apply without overriding an already-configured app
    ``log_dir``.
    """
    if _logging_state.host:
        return None
    existing = _existing_handler_file()
    if existing is not None:
        return existing
    return setup_logging(
        resolve_log_dir(log_dir),
        level=level,
        debug=debug,
        max_bytes=max_bytes,
        backup_count=backup_count,
    )


def current_log_file(log_dir: Path) -> Path:
    """Return the path of today's log file (without creating it)."""
    return Path(log_dir).expanduser().resolve() / _today_log_filename()


def teardown_logging() -> None:
    """Remove file handlers installed by ``setup_logging``."""
    _logging_state.host = False
    pkg_logger = logging.getLogger("octop_harness")
    for handler in list(pkg_logger.handlers):
        if getattr(handler, "name", None) == _HANDLER_NAME:
            handler.close()
            pkg_logger.removeHandler(handler)
    _log_agent_id.set(None)


__all__ = [
    "DEFAULT_LOG_BACKUP_COUNT",
    "DEFAULT_LOG_MAX_BYTES",
    "LogLevel",
    "current_log_agent_id",
    "current_log_file",
    "default_log_dir",
    "ensure_logging",
    "logging_scope",
    "resolve_log_dir",
    "setup_logging",
    "teardown_logging",
    "use_host_logging",
]
