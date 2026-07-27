"""PostgreSQL dump/restore via client tools on PATH."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from octop.infra.errors import ErrorCode, OctopError


def _require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            f"{name} not found on PATH; required for PostgreSQL backup/restore",
        )
    return path


def dump_postgres(conninfo: str, dest: Path) -> None:
    pg_dump = _require_tool("pg_dump")
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [pg_dump, "-Fc", "-f", str(dest), "--dbname", conninfo],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            f"pg_dump failed: {proc.stderr.strip() or proc.stdout.strip()}",
        )


def restore_postgres(conninfo: str, dump_file: Path) -> None:
    pg_restore = _require_tool("pg_restore")
    proc = subprocess.run(
        [
            pg_restore,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--dbname",
            conninfo,
            str(dump_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # pg_restore may return 1 with warnings; treat only >=2 as hard fail.
    if proc.returncode >= 2:
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            f"pg_restore failed: {proc.stderr.strip() or proc.stdout.strip()}",
        )
