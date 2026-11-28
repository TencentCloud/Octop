"""Offline SQLite health inspection and recovery for ``OCTOP_HOME``."""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import tempfile
import uuid
from contextlib import closing, suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

_SQLITE_SUFFIXES = frozenset({".db", ".sqlite"})
_SKIP_DIR_NAMES = frozenset({"backups", ".git", "__pycache__"})
_SKIP_MARKERS = (".bak", ".tmp", ".corrupt", ".recovered", ".recovering", ".migrated-")


@dataclass(frozen=True)
class SqliteCheckReport:
    """Read-only integrity summary for one SQLite file."""

    path: str
    ok: bool
    size_bytes: int
    wal_bytes: int
    shm_bytes: int
    journal_mode: str | None
    messages: list[str]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SqliteRecoveryResult:
    """Outcome of recovering or resetting one SQLite file."""

    path: str
    mode: Literal["recover", "reset"]
    method: Literal["sqlite3_recover", "python_iterdump", "reset"]
    backup_path: str
    ok: bool
    messages: list[str]
    size_before: int
    size_after: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_candidate_sqlite_file(path: Path) -> bool:
    if path.suffix.lower() not in _SQLITE_SUFFIXES:
        return False
    lower = path.name.lower()
    return not any(marker in lower for marker in _SKIP_MARKERS)


def discover_sqlite_files(root: Path) -> list[Path]:
    """Return every active SQLite database under *root* (``octop.db`` first)."""
    resolved_root = root.expanduser()
    if not resolved_root.is_dir():
        return []

    found: list[Path] = []
    seen: set[Path] = set()

    def _add(candidate: Path) -> None:
        if not candidate.is_file() or candidate.is_symlink():
            return
        if not _is_candidate_sqlite_file(candidate):
            return
        try:
            key = candidate.resolve()
        except OSError:
            key = candidate
        if key not in seen:
            seen.add(key)
            found.append(key)

    _add(resolved_root / "octop.db")

    for dirpath, dirnames, filenames in os.walk(resolved_root):
        dirnames[:] = sorted(name for name in dirnames if name not in _SKIP_DIR_NAMES)
        current = Path(dirpath)
        for name in sorted(filenames):
            _add(current / name)

    return found


def _sidecar_size(path: Path, suffix: str) -> int:
    try:
        return path.with_name(path.name + suffix).stat().st_size
    except OSError:
        return 0


def inspect_sqlite_file(path: Path, *, full: bool = False) -> SqliteCheckReport:
    """Run ``PRAGMA quick_check`` (or ``integrity_check``) on *path* read-only."""
    target = path.expanduser()
    try:
        resolved = target.resolve(strict=True)
        size_bytes = resolved.stat().st_size
    except OSError as exc:
        return SqliteCheckReport(
            path=str(target),
            ok=False,
            size_bytes=0,
            wal_bytes=0,
            shm_bytes=0,
            journal_mode=None,
            messages=[],
            error=str(exc),
        )

    wal_bytes = _sidecar_size(resolved, "-wal")
    shm_bytes = _sidecar_size(resolved, "-shm")
    journal_mode: str | None = None
    pragma = "PRAGMA integrity_check" if full else "PRAGMA quick_check"

    try:
        with closing(
            sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True, timeout=2.0)
        ) as conn:
            conn.execute("PRAGMA query_only = ON")
            jm_row = conn.execute("PRAGMA journal_mode").fetchone()
            if jm_row is not None:
                journal_mode = str(jm_row[0])
            rows = conn.execute(pragma).fetchall()
            messages = [str(row[0]) for row in rows]
    except sqlite3.Error as exc:
        return SqliteCheckReport(
            path=str(resolved),
            ok=False,
            size_bytes=size_bytes,
            wal_bytes=wal_bytes,
            shm_bytes=shm_bytes,
            journal_mode=journal_mode,
            messages=[],
            error=str(exc),
        )

    return SqliteCheckReport(
        path=str(resolved),
        ok=messages == ["ok"],
        size_bytes=size_bytes,
        wal_bytes=wal_bytes,
        shm_bytes=shm_bytes,
        journal_mode=journal_mode,
        messages=messages,
        error=None if messages == ["ok"] else "; ".join(messages[:5]),
    )


def _fsync_file(target: Path) -> None:
    with target.open("r+b") as handle:
        os.fsync(handle.fileno())


def _remove_wal_sidecars(path: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        with suppress(OSError):
            path.with_name(path.name + suffix).unlink(missing_ok=True)


def _backup_existing(target: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    token = uuid.uuid4().hex[:8]
    backup = target.with_name(f"{target.name}.corrupt-{stamp}.{token}.bak")
    shutil.copy2(target, backup)
    if os.name == "posix":
        os.chmod(backup, 0o600)
    _fsync_file(backup)
    for suffix in ("-wal", "-shm"):
        sidecar = target.with_name(target.name + suffix)
        if sidecar.is_file():
            with suppress(OSError):
                shutil.copy2(sidecar, backup.with_name(backup.name + suffix))
    return backup


def _recover_via_sqlite3_cli(sqlite3_exe: str, source: Path, dest: Path) -> bool:
    """Use ``sqlite3 .recover`` to salvage readable rows into *dest*."""
    sql_fd, sql_name = tempfile.mkstemp(dir=dest.parent, prefix=".octop-recover-", suffix=".sql")
    os.close(sql_fd)
    sql_path = Path(sql_name)
    try:
        with sql_path.open("wb") as dump_out:
            dump = subprocess.run(
                [sqlite3_exe, str(source), ".recover"],
                stdout=dump_out,
                stderr=subprocess.PIPE,
                check=False,
                timeout=300,
            )
        if dump.returncode != 0 or sql_path.stat().st_size == 0:
            return False
        dest.unlink(missing_ok=True)
        with sql_path.open("rb") as dump_in:
            load = subprocess.run(
                [sqlite3_exe, str(dest)],
                stdin=dump_in,
                capture_output=True,
                check=False,
                timeout=300,
            )
        if load.returncode != 0 or not dest.is_file() or dest.stat().st_size == 0:
            return False
        return inspect_sqlite_file(dest, full=False).ok
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        sql_path.unlink(missing_ok=True)


def _recover_via_python_iterdump(source: Path, dest: Path) -> bool:
    """Pure-Python fallback using ``sqlite3.Connection.iterdump()``."""
    dest.unlink(missing_ok=True)
    try:
        with (
            closing(sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True, timeout=5.0)) as src,
            closing(sqlite3.connect(dest, isolation_level=None, timeout=5.0)) as out,
        ):
            src.execute("PRAGMA query_only = ON")
            dumped = False
            for stmt in src.iterdump():
                dumped = True
                out.execute(stmt)
        if not dumped or not dest.is_file() or dest.stat().st_size == 0:
            return False
        return inspect_sqlite_file(dest, full=False).ok
    except sqlite3.Error:
        return False


def recover_sqlite_file(
    path: Path,
    *,
    mode: Literal["recover", "reset"] = "recover",
    sqlite3_bin: str | None = None,
) -> SqliteRecoveryResult:
    """Back up *path* and either rebuild it with SQLite recovery or reset it."""
    target = path.expanduser().resolve(strict=True)
    if not target.is_file():
        raise ValueError(f"not a file: {target}")
    size_before = target.stat().st_size
    backup = _backup_existing(target)

    if mode == "reset":
        _remove_wal_sidecars(target)
        target.unlink()
        return SqliteRecoveryResult(
            path=str(target),
            mode="reset",
            method="reset",
            backup_path=str(backup),
            ok=True,
            messages=["reset"],
            size_before=size_before,
            size_after=0,
        )

    staging = target.with_name(f"{target.name}.recovering.{uuid.uuid4().hex[:8]}.tmp")
    method: Literal["sqlite3_recover", "python_iterdump"] | None = None
    try:
        exe = sqlite3_bin if sqlite3_bin is not None else shutil.which("sqlite3")
        if exe and _recover_via_sqlite3_cli(exe, target, staging):
            method = "sqlite3_recover"
        elif _recover_via_python_iterdump(target, staging):
            method = "python_iterdump"

        if method is None:
            raise RuntimeError(
                f"Unable to recover SQLite file {target}; original backup kept at {backup}"
            )

        with closing(sqlite3.connect(staging, timeout=5.0)) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        _remove_wal_sidecars(staging)
        if os.name == "posix":
            os.chmod(staging, 0o600)
        _fsync_file(staging)
        _remove_wal_sidecars(target)
        os.replace(staging, target)
    except BaseException:
        _remove_wal_sidecars(staging)
        staging.unlink(missing_ok=True)
        raise

    verified = inspect_sqlite_file(target, full=False)
    return SqliteRecoveryResult(
        path=str(target),
        mode="recover",
        method=method,
        backup_path=str(backup),
        ok=verified.ok,
        messages=verified.messages,
        size_before=size_before,
        size_after=target.stat().st_size,
    )
