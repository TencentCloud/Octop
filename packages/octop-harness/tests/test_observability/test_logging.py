"""Tests for ``octop_harness.observability.logging``."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

import pytest

from octop_harness.observability.logging import (
    _HANDLER_NAME,
    current_log_file,
    default_log_dir,
    ensure_logging,
    logging_scope,
    resolve_log_dir,
    setup_logging,
    teardown_logging,
    use_host_logging,
)


@pytest.fixture(autouse=True)
def _clean_logging():
    """Ensure logging handlers are removed after every test."""
    yield
    teardown_logging()


class TestSetupLogging:
    def test_creates_log_dir(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        assert not log_dir.exists()
        setup_logging(log_dir)
        assert log_dir.exists()
        assert log_dir.is_dir()

    def test_returns_date_named_log_file_path(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        result = setup_logging(log_dir)
        assert re.match(r"\d{4}-\d{2}-\d{2}\.log", result.name)
        assert result.parent == log_dir

    def test_log_filename_matches_today(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        result = setup_logging(log_dir)
        today = datetime.now().astimezone().strftime("%Y-%m-%d")
        assert result.name == f"{today}.log"

    def test_file_handler_attached_to_package_logger(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        setup_logging(log_dir)
        pkg_logger = logging.getLogger("octop_harness")
        handler_names = [getattr(h, "name", None) for h in pkg_logger.handlers]
        assert _HANDLER_NAME in handler_names

    def test_default_level_is_info(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        setup_logging(log_dir)
        pkg_logger = logging.getLogger("octop_harness")
        assert pkg_logger.level == logging.INFO

    def test_debug_flag_sets_debug_level(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        setup_logging(log_dir, debug=True)
        pkg_logger = logging.getLogger("octop_harness")
        assert pkg_logger.level == logging.DEBUG

    def test_explicit_level_overrides_debug_flag(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        setup_logging(log_dir, level="WARNING", debug=True)
        pkg_logger = logging.getLogger("octop_harness")
        assert pkg_logger.level == logging.WARNING

    def test_idempotent_does_not_duplicate_handlers(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        setup_logging(log_dir)
        setup_logging(log_dir)
        setup_logging(log_dir)
        pkg_logger = logging.getLogger("octop_harness")
        matching = [h for h in pkg_logger.handlers if getattr(h, "name", None) == _HANDLER_NAME]
        assert len(matching) == 1

    def test_idempotent_updates_level_on_second_call(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        setup_logging(log_dir, level="INFO")
        setup_logging(log_dir, level="DEBUG")
        pkg_logger = logging.getLogger("octop_harness")
        assert pkg_logger.level == logging.DEBUG

    def test_log_messages_written_to_file(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        log_file = setup_logging(log_dir)
        child = logging.getLogger("octop_harness.test_child")
        child.info("hello from test")
        pkg_logger = logging.getLogger("octop_harness")
        for h in pkg_logger.handlers:
            h.flush()
        content = log_file.read_text(encoding="utf-8")
        assert "hello from test" in content
        assert "[INFO]" in content
        assert "octop_harness.test_child" in content

    def test_debug_messages_not_written_at_info_level(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        log_file = setup_logging(log_dir, level="INFO")
        child = logging.getLogger("octop_harness.test_child2")
        child.debug("should not appear")
        pkg_logger = logging.getLogger("octop_harness")
        for h in pkg_logger.handlers:
            h.flush()
        content = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
        assert "should not appear" not in content


class TestDateRollover:
    def test_date_change_creates_new_handler(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        log_dir = tmp_path / "logs"

        monkeypatch.setattr(
            "octop_harness.observability.logging._today_log_filename",
            lambda: "2026-01-15.log",
        )
        result1 = setup_logging(log_dir)
        assert result1.name == "2026-01-15.log"

        monkeypatch.setattr(
            "octop_harness.observability.logging._today_log_filename",
            lambda: "2026-01-16.log",
        )
        result2 = setup_logging(log_dir)
        assert result2.name == "2026-01-16.log"

        pkg_logger = logging.getLogger("octop_harness")
        matching = [h for h in pkg_logger.handlers if getattr(h, "name", None) == _HANDLER_NAME]
        assert len(matching) == 1


class TestCurrentLogFile:
    def test_returns_expected_path(self, tmp_path: Path) -> None:
        today = datetime.now().astimezone().strftime("%Y-%m-%d")
        result = current_log_file(tmp_path / "logs")
        assert result == tmp_path / "logs" / f"{today}.log"


class TestTeardownLogging:
    def test_removes_handler(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        setup_logging(log_dir)
        pkg_logger = logging.getLogger("octop_harness")
        assert any(getattr(h, "name", None) == _HANDLER_NAME for h in pkg_logger.handlers)
        teardown_logging()
        assert not any(getattr(h, "name", None) == _HANDLER_NAME for h in pkg_logger.handlers)

    def test_teardown_is_safe_when_not_initialized(self) -> None:
        teardown_logging()
        teardown_logging()


class TestDefaultLogDir:
    def test_default_is_under_home_octop_harness(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        assert default_log_dir() == tmp_path / ".octop-harness" / "logs"


class TestSharedLogDirAgentTag:
    def test_shared_log_dir_keeps_single_handler(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        setup_logging(log_dir)
        setup_logging(log_dir)
        pkg_logger = logging.getLogger("octop_harness")
        matching = [h for h in pkg_logger.handlers if getattr(h, "name", None) == _HANDLER_NAME]
        assert len(matching) == 1

    def test_different_log_dir_replaces_handler(self, tmp_path: Path) -> None:
        a = tmp_path / "a"
        b = tmp_path / "b"
        setup_logging(a)
        setup_logging(b)
        pkg_logger = logging.getLogger("octop_harness")
        matching = [h for h in pkg_logger.handlers if getattr(h, "name", None) == _HANDLER_NAME]
        assert len(matching) == 1
        assert Path(matching[0].baseFilename).parent == b.resolve()

    def test_lines_include_agent_tag(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        log_file = setup_logging(log_dir)
        with logging_scope("4JSSSJ"):
            logging.getLogger("octop_harness.scope").warning("disk-check")
        for h in logging.getLogger("octop_harness").handlers:
            h.flush()
        text = log_file.read_text(encoding="utf-8")
        assert "[agent=4JSSSJ]" in text
        assert "disk-check" in text

    def test_missing_scope_uses_dash(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        log_file = setup_logging(log_dir)
        logging.getLogger("octop_harness.scope").warning("no-agent")
        for h in logging.getLogger("octop_harness").handlers:
            h.flush()
        text = log_file.read_text(encoding="utf-8")
        assert "[agent=-]" in text
        assert "no-agent" in text

    def test_two_agents_share_one_file(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "logs"
        log_file = setup_logging(log_dir)
        with logging_scope("agent-a"):
            logging.getLogger("octop_harness.scope").warning("only-a")
        with logging_scope("agent-b"):
            logging.getLogger("octop_harness.scope").warning("only-b")
        for h in logging.getLogger("octop_harness").handlers:
            h.flush()
        text = log_file.read_text(encoding="utf-8")
        assert "[agent=agent-a]" in text
        assert "[agent=agent-b]" in text
        assert "only-a" in text
        assert "only-b" in text


class TestResolveLogDir:
    def test_none_uses_library_default(self) -> None:
        assert resolve_log_dir(None) == default_log_dir().resolve()

    def test_relative_anchors_to_library_default(self) -> None:
        assert resolve_log_dir("nested") == (default_log_dir() / "nested").resolve()

    def test_absolute_is_unchanged(self, tmp_path: Path) -> None:
        target = tmp_path / "custom"
        assert resolve_log_dir(target) == target.resolve()


class TestEnsureLogging:
    def test_installs_default_when_unconfigured(self) -> None:
        log_file = ensure_logging()
        assert log_file.parent == default_log_dir().resolve()
        pkg_logger = logging.getLogger("octop_harness")
        matching = [h for h in pkg_logger.handlers if getattr(h, "name", None) == _HANDLER_NAME]
        assert len(matching) == 1

    def test_does_not_override_existing_handler(self, tmp_path: Path) -> None:
        app_dir = tmp_path / "app-logs"
        expected = setup_logging(app_dir)
        result = ensure_logging()
        assert result == expected
        pkg_logger = logging.getLogger("octop_harness")
        matching = [h for h in pkg_logger.handlers if getattr(h, "name", None) == _HANDLER_NAME]
        assert len(matching) == 1
        assert Path(matching[0].baseFilename).parent == app_dir.resolve()

    def test_host_logging_skips_package_file(self, tmp_path: Path) -> None:
        setup_logging(tmp_path / "dated")
        use_host_logging()
        assert ensure_logging() is None
        pkg_logger = logging.getLogger("octop_harness")
        assert pkg_logger.handlers == []
        assert pkg_logger.propagate is True
