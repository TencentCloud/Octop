"""Tests for Windows harness execute compatibility patches."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from harness_agent.backends import bwrap_shell

from octop.infra.backend import windows_execute


def _fake_backend(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        _default_timeout=30,
        _max_output_bytes=100_000,
        _env=os.environ.copy(),
        cwd=str(tmp_path),
    )


def test_patched_execute_decodes_utf8_cleanly(tmp_path: Path) -> None:
    backend = _fake_backend(tmp_path)
    fake_run = SimpleNamespace(stdout=b"\xe4\xbd\xa0\xe5\xa5\xbd\n", stderr=b"", returncode=0)
    with patch("octop.infra.backend.windows_execute.subprocess.run", return_value=fake_run):
        res = windows_execute._patched_execute(backend, "python tts.py")
    assert res.exit_code == 0
    assert res.output == "你好\n"


def test_patched_execute_normalizes_crlf_like_text_mode(tmp_path: Path) -> None:
    # Original deepagents uses subprocess.run(..., text=True), whose universal
    # newlines collapse CRLF from Windows native tools to LF. Bytes mode must
    # mirror that so output stays identical for valid UTF-8 streams.
    backend = _fake_backend(tmp_path)
    fake_run = SimpleNamespace(stdout=b"hi\r\nline2\r\n", stderr=b"", returncode=0)
    with patch("octop.infra.backend.windows_execute.subprocess.run", return_value=fake_run):
        res = windows_execute._patched_execute(backend, "dir")
    assert res.exit_code == 0
    assert res.output == "hi\nline2\n"


def test_patched_execute_tolerates_gbk_bytes(tmp_path: Path) -> None:
    # Chinese-Windows native tools emit GBK; the strict UTF-8 reader used to
    # crash and drop the whole output. The patched reader must not raise.
    backend = _fake_backend(tmp_path)
    fake_run = SimpleNamespace(stdout="中".encode("gbk"), stderr=b"", returncode=0)
    with patch("octop.infra.backend.windows_execute.subprocess.run", return_value=fake_run):
        res = windows_execute._patched_execute(backend, "dir")
    assert res.exit_code == 0
    assert "\ufffd" in res.output
    assert "<no output>" not in res.output


def test_patched_execute_prefixes_stderr_and_exit_code(tmp_path: Path) -> None:
    backend = _fake_backend(tmp_path)
    fake_run = SimpleNamespace(stdout=b"out", stderr=b"err1\nerr2", returncode=1)
    with patch("octop.infra.backend.windows_execute.subprocess.run", return_value=fake_run):
        res = windows_execute._patched_execute(backend, "bad cmd")
    assert res.exit_code == 1
    assert res.output == "out\n[stderr] err1\n[stderr] err2\n\nExit code: 1"


def test_patched_execute_timeout_returns_124(tmp_path: Path) -> None:
    backend = _fake_backend(tmp_path)
    with patch(
        "octop.infra.backend.windows_execute.subprocess.run",
        side_effect=subprocess.TimeoutExpired("cmd", 30),
    ):
        res = windows_execute._patched_execute(backend, "sleep 10")
    assert res.exit_code == 124
    assert "timed out" in res.output


def test_patched_execute_invalid_command(tmp_path: Path) -> None:
    backend = _fake_backend(tmp_path)
    res = windows_execute._patched_execute(backend, "")
    assert res.exit_code == 1
    assert "non-empty" in res.output


def _windows_safe_regex() -> re.Pattern[str]:
    pattern = bwrap_shell._ABS_TOKEN_RE.pattern
    return re.compile(pattern.replace(r"(?<![\w/.])", r"(?<![\w/:.\\])"))


def test_drive_path_rewrite_leaves_windows_abs_paths(tmp_path: Path) -> None:
    original = bwrap_shell._ABS_TOKEN_RE
    try:
        bwrap_shell._ABS_TOKEN_RE = _windows_safe_regex()
        cmd = "C:/Users/Lenovo/.octop-venv/Scripts/python.exe -V"
        out = bwrap_shell.rewrite_virtual_paths_in_command(cmd, str(tmp_path))
        assert out == cmd
    finally:
        bwrap_shell._ABS_TOKEN_RE = original


def test_drive_path_rewrite_keeps_mapping_virtual_paths(tmp_path: Path) -> None:
    original = bwrap_shell._ABS_TOKEN_RE
    try:
        bwrap_shell._ABS_TOKEN_RE = _windows_safe_regex()
        out = bwrap_shell.rewrite_virtual_paths_in_command("cat /AGENTS.md", str(tmp_path))
        assert str(tmp_path) in out
        assert "AGENTS.md" in out
    finally:
        bwrap_shell._ABS_TOKEN_RE = original


@pytest.mark.skipif(os.name != "nt", reason="Windows-only patch")
def test_apply_is_idempotent_on_windows() -> None:
    saved = windows_execute._APPLIED
    windows_execute._APPLIED = False
    try:
        assert windows_execute.apply() is True
        assert windows_execute.apply() is False
    finally:
        windows_execute._APPLIED = saved


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only no-op")
def test_apply_is_noop_on_posix() -> None:
    assert windows_execute.apply() is False
