"""PostgreSQL dump/restore via client tools on PATH."""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from octop.infra.errors import ErrorCode, OctopError


# Known pg_dump/pg_restore install locations that shutil.which misses in
# Docker containers, minimal distros and non-standard prefix builds.
_KNOWN_PG_BIN_DIRS: tuple[str, ...] = (
    # Docker images: official postgres debian base
    "/usr/bin",
    "/usr/local/bin",
    # RHEL/Fedora system packages
    "/usr/pgsql-16/bin",
    "/usr/pgsql-15/bin",
    "/usr/pgsql-14/bin",
    "/usr/pgsql-13/bin",
    "/usr/pgsql-12/bin",
    # Homebrew on macOS
    "/opt/homebrew/bin",
    "/usr/local/opt/postgresql/bin",
    "/usr/local/opt/postgresql@16/bin",
    "/usr/local/opt/postgresql@15/bin",
    "/usr/local/opt/postgresql@14/bin",
    # Source installs / conda
    "/opt/postgres/bin",
    "/opt/pg/bin",
)


def _scan_known_dirs(name: str) -> str | None:
    for directory in _KNOWN_PG_BIN_DIRS:
        candidate = Path(directory) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    # Glob PostgreSQL versioned directories (e.g. /usr/pgsql-*/bin/pg_dump)
    for pattern in ("/usr/pgsql-*/bin", "/opt/postgres-*/bin"):
        for directory in sorted(glob.glob(pattern)):
            candidate = Path(directory) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    # Windows common install paths
    for root in ("C:\\Program Files\\PostgreSQL", "C:\\Program Files (x86)\\PostgreSQL"):
        if not os.path.isdir(root):
            continue
        for version_dir in sorted(os.listdir(root)):
            candidate = Path(root) / version_dir / "bin" / f"{name}.exe"
            if candidate.is_file():
                return str(candidate)
    return None


def _tool_candidates(name: str) -> list[str]:
    """Return candidate paths for *name* in priority order."""
    candidates: list[str] = []
    # 1. shutil.which (PATH)
    found = shutil.which(name)
    if found:
        candidates.append(found)
    # 2. Explicit env override
    pg_bin = os.getenv("PG_BIN") or os.getenv("POSTGRES_BIN") or os.getenv("OCTOP_PG_BIN")
    if pg_bin:
        explicit = Path(pg_bin) / name
        if explicit.is_file():
            candidates.append(str(explicit))
    # 3. Known install locations
    scanned = _scan_known_dirs(name)
    if scanned:
        candidates.append(scanned)
    return candidates


def _require_tool(name: str) -> str:
    """Resolve ``pg_dump`` / ``pg_restore`` against PATH + known fallback dirs."""
    candidates = _tool_candidates(name)
    if not candidates:
        raise OctopError(
            ErrorCode.INTERNAL_ERROR,
            f"{name} not found on PATH or any known PostgreSQL bin directory; "
            f"install postgresql-client or set PG_BIN / OCTOP_PG_BIN",
        )
    path = candidates[0]
    # Augment PATH for subprocess so it finds any sibling tools (e.g. pg_restore
    # after pg_dump was resolved via a fallback dir).
    pg_dir = str(Path(path).parent)
    existing_path = os.environ.get("PATH", "")
    if pg_dir not in existing_path.split(os.pathsep):
        os.environ["PATH"] = pg_dir + os.pathsep + existing_path
    return path


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