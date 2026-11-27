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
            ErrorCode.BACKUP_CLIENT_MISSING,
            f"{name} not found on PATH; required for PostgreSQL backup/restore",
            details={"tool": name},
        )
    return path


def postgres_dump_data_exclusions(
    *,
    include_chats: bool,
    chat_tables: Sequence[str],
) -> tuple[str, ...]:
    """Tables whose rows stay out of a backup dump.

    ``secrets`` holds the session signing key and other instance credentials.
    Those rows are restored from the running instance, not from the archive.
    """
    names = ["secrets"]
    if not include_chats:
        names.extend(chat_tables)
    return tuple(names)


def dump_contains_table_data(dump_file: Path, table: str) -> bool:
    """Return whether a custom-format dump still carries ``table`` row data.

    Missing ``pg_restore`` fails closed: the dump is treated as if the rows
    are present, so a caller can refuse to hand the file out.
    """
    pg_restore = shutil.which("pg_restore")
    if pg_restore is None:
        return True
    proc = subprocess.run(
        [pg_restore, "-l", str(dump_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return True
    return any(toc_line_has_table_data(line, table) for line in proc.stdout.splitlines())


def toc_line_has_table_data(line: str, table: str) -> bool:
    """Return whether one ``pg_restore -l`` line is ``TABLE DATA`` for *table*.

    Example: ``3220; 0 16587 TABLE DATA public secrets postgres``.
    """
    parts = line.split()
    return len(parts) >= 7 and parts[3] == "TABLE" and parts[4] == "DATA" and parts[6] == table


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
    # pg tools write diagnostics in the database encoding (UTF-8); the parent
    # must not inherit the ANSI locale, whose strict decode can crash on the
    # very message that reports a failure.
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
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
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    # pg_restore may return 1 with warnings; treat only >=2 as hard fail.
    if proc.returncode >= 2:
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            f"pg_restore failed: {proc.stderr.strip() or proc.stdout.strip()}",
        )
