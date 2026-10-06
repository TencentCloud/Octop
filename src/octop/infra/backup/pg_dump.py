"""PostgreSQL dump/restore via client tools on PATH."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from octop.infra.errors import ErrorCode, OctopError


def _require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise OctopError(
            ErrorCode.BACKUP_TOOL_MISSING,
            f"{name} not found on PATH; required for PostgreSQL backup/restore. "
            "Install the PostgreSQL client tools (e.g. apt-get install postgresql-client "
            "inside the container, or mount the host binary) and retry.",
        )
    return path


_VERSION_MISMATCH_MARKER = "server version mismatch"


def _failure_error(
    name: str,
    proc: subprocess.CompletedProcess[str],
) -> OctopError:
    detail = (proc.stderr or "").strip() or (proc.stdout or "").strip()
    if _VERSION_MISMATCH_MARKER in detail:
        return OctopError(
            ErrorCode.BACKUP_TOOL_MISMATCH,
            f"{name} aborted because the installed client tools do not match the "
            f"server major version: {detail}. Install a postgresql-client build "
            "matching the server major version (e.g. postgresql-client-18) and retry.",
        )
    return OctopError(ErrorCode.INTERNAL_ERROR, f"{name} failed: {detail}")


def _mentions_version_mismatch(proc: subprocess.CompletedProcess[str]) -> bool:
    return _VERSION_MISMATCH_MARKER in ((proc.stderr or "") + (proc.stdout or ""))


def dump_postgres(
    conninfo: str,
    dest: Path,
    *,
    exclude_table_data: Sequence[str] = (),
) -> None:
    pg_dump = _require_tool("pg_dump")
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [pg_dump, "-Fc", "-f", str(dest), "--dbname", conninfo]
    for table in exclude_table_data:
        cmd.extend(["--exclude-table-data", table])
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise _failure_error("pg_dump", proc)


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
    # A version-mismatch abort also exits 1, so it is raised before the
    # threshold can swallow it (#1301).
    if proc.returncode != 0 and _mentions_version_mismatch(proc):
        raise _failure_error("pg_restore", proc)
    if proc.returncode >= 2:
        raise _failure_error("pg_restore", proc)
