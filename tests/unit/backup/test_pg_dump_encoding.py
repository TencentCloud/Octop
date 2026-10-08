from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from tests.support.fakes import fake_bin_path

from octop.infra.backup import pg_dump
from octop.infra.errors import OctopError


@pytest.mark.parametrize("locale_encoding", ["utf-8", "cp936"])
@pytest.mark.parametrize("stream", ["stdout", "stderr"])
@pytest.mark.parametrize("invalid_byte", [False, True], ids=["utf8", "invalid-byte"])
@pytest.mark.parametrize(
    ("tool", "returncode", "fails"),
    [
        ("pg_dump", 0, False),
        ("pg_dump", 1, True),
        ("pg_restore", 0, False),
        ("pg_restore", 1, False),
        ("pg_restore", 2, True),
    ],
)
def test_pg_tool_diagnostics_do_not_depend_on_locale(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    locale_encoding: str,
    stream: str,
    invalid_byte: bool,
    tool: str,
    returncode: int,
    fails: bool,
) -> None:
    diagnostic = "订单数据".encode() + (b"\xff" if invalid_byte else b"")
    expected = "订单数据" + ("\ufffd" if invalid_byte else "")
    script = f"import sys; sys.{stream}.buffer.write({diagnostic!r}); sys.exit({returncode})"
    real_run = subprocess.run
    results: list[subprocess.CompletedProcess[str]] = []

    def run_tool(_command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        # Emulate the host code page while exercising real subprocess pipe decoding.
        kwargs.setdefault("encoding", locale_encoding)
        result = real_run([sys.executable, "-c", script], **kwargs)
        results.append(result)
        return result

    monkeypatch.setattr(pg_dump, "_require_tool", fake_bin_path)
    monkeypatch.setattr(pg_dump.subprocess, "run", run_tool)
    operation = pg_dump.dump_postgres if tool == "pg_dump" else pg_dump.restore_postgres
    dump_file = tmp_path / "backup.dump"

    if fails:
        with pytest.raises(OctopError) as exc_info:
            operation("postgresql://example", dump_file)
        assert str(exc_info.value) == f"{tool} failed: {expected}"
    else:
        operation("postgresql://example", dump_file)

    assert len(results) == 1
    assert getattr(results[0], stream) == expected
