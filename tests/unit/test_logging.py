"""tests/unit/test_logging.py

Covers the daily-rotation + retention logging strategy in ``octop.infra.server``:
the log path lives under ``~/.octop/logs`` and stale rotated files are purged.
"""

from __future__ import annotations

import logging
import os
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import pytest

from octop.infra.server import (
    OctopServer,
    _attach_log_handler,
    _build_log_handler,
    _purge_stale_logs,
)


@pytest.fixture(autouse=True)
def _isolate_root_logger() -> None:
    """Restore the global root/uvicorn loggers so tests never leak handlers/levels."""
    root = logging.getLogger()
    saved_root_handlers = list(root.handlers)
    saved_root_level = root.level
    saved_child = {
        name: list(logging.getLogger(name).handlers)
        for name in ("uvicorn", "uvicorn.access", "uvicorn.error")
    }
    yield
    root.handlers = saved_root_handlers
    root.setLevel(saved_root_level)
    for name, handlers in saved_child.items():
        logging.getLogger(name).handlers = handlers


def _stale_path(log_dir: Path, name: str, age_days: int) -> Path:
    """Create a rotated log file with an mtime shifted ``age_days`` into the past."""
    path = log_dir / name
    path.write_text("old\n", encoding="utf-8")
    past = time.time() - age_days * 86400
    os.utime(path, (past, past))
    return path


def test_build_log_handler_uses_daily_rotation_and_retention(tmp_path: Path):
    handler = _build_log_handler(tmp_path / "octop.log", retention_days=7)
    try:
        assert isinstance(handler, TimedRotatingFileHandler)
        assert handler.when == "MIDNIGHT"
        assert handler.backupCount == 7
        # Date-only suffix keeps filenames valid on Windows (no ':' like %H:%M:%S).
        assert handler.suffix == "%Y-%m-%d"
        assert ":" not in handler.suffix
    finally:
        handler.close()


def test_purge_stale_logs_removes_only_old_files(tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    old = _stale_path(log_dir, "octop.log.2020-01-01", age_days=100)
    new = _stale_path(log_dir, "octop.log.2026-07-16", age_days=1)

    _purge_stale_logs(log_dir, retention_days=14)

    assert not old.exists()
    assert new.exists()


def test_purge_stale_logs_skipped_when_retention_non_positive(tmp_path: Path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    old = _stale_path(log_dir, "octop.log.2020-01-01", age_days=100)

    _purge_stale_logs(log_dir, retention_days=0)

    assert old.exists()


def test_attach_log_handler_is_idempotent(tmp_path: Path):
    root = logging.getLogger()
    handler = _build_log_handler(tmp_path / "octop.log", retention_days=7)
    try:
        _attach_log_handler(root, handler)
        _attach_log_handler(root, handler)
        matching = [
            h
            for h in root.handlers
            if isinstance(h, TimedRotatingFileHandler) and h.baseFilename == handler.baseFilename
        ]
        assert len(matching) == 1
    finally:
        handler.close()


def test_setup_logging_creates_logs_dir_and_file(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OCTOP_LOG_LEVEL", raising=False)
    monkeypatch.delenv("OCTOP_LOG_RETENTION_DAYS", raising=False)
    server = OctopServer(home=tmp_path / ".octop")

    server._setup_logging()

    assert server.paths.logs_dir.is_dir()
    root = logging.getLogger()
    handler = next(
        h
        for h in root.handlers
        if isinstance(h, TimedRotatingFileHandler) and h.baseFilename == str(server.paths.log)
    )
    # Emit a record and confirm it lands in the logs directory file.
    root.info("logging smoke test")
    handler.flush()
    assert server.paths.log.exists()
    assert "logging smoke test" in server.paths.log.read_text(encoding="utf-8")
    assert root.level == logging.INFO


def test_setup_logging_migrates_legacy_log(tmp_path: Path):
    home = tmp_path / ".octop"
    legacy = home / "octop.log"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("legacy content", encoding="utf-8")
    server = OctopServer(home=home)

    server._setup_logging()

    assert not legacy.exists()
    assert server.paths.log.exists()
    assert server.paths.log.read_text(encoding="utf-8") == "legacy content"


def test_setup_logging_respects_retention_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OCTOP_LOG_RETENTION_DAYS", "3")
    server = OctopServer(home=tmp_path / ".octop")

    server._setup_logging()

    root = logging.getLogger()
    handler = next(
        h
        for h in root.handlers
        if isinstance(h, TimedRotatingFileHandler) and h.baseFilename == str(server.paths.log)
    )
    assert handler.backupCount == 3


def test_setup_logging_respects_level_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OCTOP_LOG_LEVEL", "debug")
    server = OctopServer(home=tmp_path / ".octop")

    server._setup_logging()

    assert logging.getLogger().level == logging.DEBUG


def test_setup_logging_falls_back_on_invalid_level_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OCTOP_LOG_LEVEL", "not-a-level")
    server = OctopServer(home=tmp_path / ".octop")

    server._setup_logging()

    assert logging.getLogger().level == logging.INFO


def test_setup_logging_falls_back_on_invalid_retention_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OCTOP_LOG_RETENTION_DAYS", "oops")
    server = OctopServer(home=tmp_path / ".octop")

    server._setup_logging()

    root = logging.getLogger()
    handler = next(
        h
        for h in root.handlers
        if isinstance(h, TimedRotatingFileHandler) and h.baseFilename == str(server.paths.log)
    )
    # Default retention is 14 days.
    assert handler.backupCount == 14
