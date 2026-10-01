"""``pg_dump`` / ``pg_restore`` failures have to report the tool's message.

The PostgreSQL client tools print database identifiers in the cluster's encoding, so a failed
dump can put bytes on the pipe that no platform codec accepts. ``subprocess.run(..., text=True)``
without an explicit ``encoding`` decodes them with ``locale.getpreferredencoding()``, the decode
raises inside Python's ``_readerthread``, and ``stderr`` arrives as ``None`` — the error branch
then dies on ``AttributeError: 'NoneType' object has no attribute 'strip'`` and the API returns a
bare 500 instead of saying why the backup failed.

Every case below runs a real stub tool through ``PATH``, so the assertions cover the decode path
itself rather than the keyword arguments.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from octop.infra.backup.pg_dump import dump_postgres, restore_postgres
from octop.infra.errors import OctopError

CONNINFO = "postgresql://octop@127.0.0.1:5432/octop"

# ``中文表`` the way a UTF-8 cluster prints it, then 0x81 — a byte that UTF-8, cp936 and cp1252
# all reject, so a run that decodes with the platform codec loses the whole message on any CI.
TOOL_STDERR = (
    b'pg_dump: error: dump of object "\xe4\xb8\xad\xe6\x96\x87\xe8\xa1\xa8" -> aborting\n'
    b"pg_dump: error: rejected byte \x81 in name\n"
)


def _install_fake_tool(tmp_path: Path, name: str, *, returncode: int) -> None:
    """Put ``name`` first on ``PATH``: write ``TOOL_STDERR``, exit with ``returncode``."""
    emitter = tmp_path / f"{name}-emit.py"
    emitter.write_text(
        "import sys\n"
        f"sys.stderr.buffer.write(bytes.fromhex({TOOL_STDERR.hex()!r}))\n"
        "sys.stderr.flush()\n"
        f"sys.exit({returncode})\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        (tmp_path / f"{name}.cmd").write_text(
            f'@"{sys.executable}" "{emitter}"\n',
            encoding="utf-8",
        )
    else:
        wrapper = tmp_path / name
        wrapper.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{emitter}"\n',
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
    assert shutil.which(name), f"{name} not resolvable on the patched PATH"


@pytest.fixture
def tools_on_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")
    return tmp_path


def test_dump_failure_keeps_the_tools_message(tools_on_path: Path) -> None:
    _install_fake_tool(tools_on_path, "pg_dump", returncode=3)

    with pytest.raises(OctopError) as captured:
        dump_postgres(CONNINFO, tools_on_path / "backup" / "db.dump")

    message = captured.value.message
    assert message.startswith("pg_dump failed:"), message
    # the ASCII around the undecodable byte survives
    assert "pg_dump: error:" in message
    assert "-> aborting" in message
    # and the identifier the cluster printed as UTF-8 is decoded, not replaced
    assert "\u4e2d\u6587\u8868" in message


def test_restore_failure_keeps_the_tools_message(tools_on_path: Path) -> None:
    _install_fake_tool(tools_on_path, "pg_restore", returncode=3)

    with pytest.raises(OctopError) as captured:
        restore_postgres(CONNINFO, tools_on_path / "db.dump")

    message = captured.value.message
    assert message.startswith("pg_restore failed:"), message
    assert "\u4e2d\u6587\u8868" in message


def test_dump_warning_on_success_is_not_reported(tools_on_path: Path) -> None:
    """A zero exit stays zero: undecodable bytes must not turn into a failure."""
    _install_fake_tool(tools_on_path, "pg_dump", returncode=0)

    dump_postgres(CONNINFO, tools_on_path / "backup" / "db.dump")
