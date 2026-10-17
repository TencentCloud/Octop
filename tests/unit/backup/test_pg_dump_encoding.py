"""Unit tests: pg_dump/pg_restore diagnostics are decoded as UTF-8 regardless of locale."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from octop.infra.backup import pg_dump
from octop.infra.errors import OctopError


def _fake_tool(tmp_path: Path, name: str, *, exit_code: int, stderr_text: str) -> str:
    """Write a stand-in pg tool that emits UTF-8 text on stderr and exits with a code.

    The payload rides inside the child code as hex because cmd.exe parses batch
    files in the ANSI codepage and would otherwise mangle non-ASCII bytes.
    """
    code = (
        "import sys;"
        f"sys.stderr.buffer.write(bytes.fromhex('{stderr_text.encode('utf-8').hex()}'));"
        f"sys.exit({exit_code})"
    )
    if os.name == "nt":
        shim = tmp_path / f"{name}.cmd"
        shim.write_bytes(f'@"{sys.executable}" -c "{code}" %*\r\n'.encode("mbcs"))
    else:
        shim = tmp_path / name
        shim.write_bytes(f'#!/bin/sh\nexec "{sys.executable}" -c "{code}" "$@"\n'.encode())
        shim.chmod(0o755)
    return str(shim)


def test_dump_failure_diagnostic_keeps_chinese_intact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A failed dump raises OctopError carrying the tool's UTF-8 message, not a decode crash.

    pg tools report in the database encoding (UTF-8); without a pinned codec the
    parent inherits the ANSI locale (cp936 on Chinese Windows): the strict decode
    raises on POSIX, while on Windows the pipe reader thread dies and silently
    turns stderr into None — the failure path then crashes with AttributeError
    instead of reporting the real pg_dump error.
    """
    monkeypatch.setattr(
        pg_dump,
        "_require_tool",
        lambda _name: _fake_tool(
            tmp_path,
            "pg_dump",
            exit_code=1,
            stderr_text="pg_dump: 错误：无法导出表 邮箱订单数据",
        ),
    )
    with pytest.raises(OctopError) as ei:
        pg_dump.dump_postgres("postgresql://example", tmp_path / "backup.dump")
    assert "邮箱订单数据" in str(ei.value)


def test_restore_hard_failure_diagnostic_keeps_chinese_intact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A hard restore failure (exit >= 2) must report the tool's UTF-8 message intact."""
    monkeypatch.setattr(
        pg_dump,
        "_require_tool",
        lambda _name: _fake_tool(
            tmp_path,
            "pg_restore",
            exit_code=2,
            stderr_text="pg_restore: 错误：恢复 邮箱订单数据 失败",
        ),
    )
    with pytest.raises(OctopError) as ei:
        pg_dump.restore_postgres("postgresql://example", tmp_path / "backup.dump")
    assert "邮箱订单数据" in str(ei.value)


def test_restore_warn_exit_tolerates_chinese_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """pg_restore exits 1 on recoverable warnings — the decode must not kill a good restore.

    On non-UTF-8 POSIX locales the strict decode raises out of subprocess.run and
    aborts an otherwise-successful restore; on Windows the reader thread dies and
    the diagnostics are silently lost.
    """
    monkeypatch.setattr(
        pg_dump,
        "_require_tool",
        lambda _name: _fake_tool(
            tmp_path,
            "pg_restore",
            exit_code=1,
            stderr_text="pg_restore: warning: 恢复对象 邮箱订单数据 时被跳过",
        ),
    )
    pg_dump.restore_postgres("postgresql://example", tmp_path / "backup.dump")


def test_dump_success_tolerates_chinese_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Warnings on a successful dump (exit 0) must not abort the backup either."""
    monkeypatch.setattr(
        pg_dump,
        "_require_tool",
        lambda _name: _fake_tool(
            tmp_path,
            "pg_dump",
            exit_code=0,
            stderr_text="pg_dump: warning: 已跳过 邮箱订单数据 的所有权设置",
        ),
    )
    pg_dump.dump_postgres("postgresql://example", tmp_path / "backup.dump")
