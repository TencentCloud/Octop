"""SQL migrations owned by ``octop.extensions`` packages.

An extension's ``migrations()`` hook returns an :class:`ExtensionMigrations`:
a namespace and a directory of ``NNN_description.sql`` / ``NNN_description.pg.sql``
files, numbered from ``001`` independently of Octop's own migrations. Each
namespace keeps its own watermark in ``_extension_schema``, so an extension's
tables never take, or collide with, Octop's next migration number.

Files run after Octop's migrations, in version order. Each file runs in one
transaction together with its watermark update, under a lock shared by every
connection and process (SQLite ``BEGIN IMMEDIATE``, PostgreSQL a transaction
advisory lock), and the watermark is re-read under that lock. A file that fails
leaves nothing behind and can simply be retried; two processes starting at once
run each file exactly once. Statements are split at a ``;`` that ends a line, so
keep one statement per ``;`` line (no trigger bodies).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from octop.infra.db.pool import DatabasePool

logger = logging.getLogger(__name__)

_NAMESPACE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SQL_STMT_RE = re.compile(r";\s*\n")

# pg_advisory_xact_lock key shared by every process applying extension migrations.
_PG_LOCK_KEY = 0x6F63746F705F6578  # "octop_ex"

_CREATE_TABLE = (
    "CREATE TABLE IF NOT EXISTS _extension_schema ("
    "namespace TEXT PRIMARY KEY, version INTEGER NOT NULL)"
)


@dataclass(frozen=True)
class ExtensionMigrations:
    namespace: str
    directory: Path


def discover(directory: Path, dialect: str) -> list[tuple[int, Path]]:
    """``(version, file)`` pairs for ``dialect``, sorted; duplicate versions are an error."""
    pattern = r"^(\d{3})_.*\.pg\.sql$" if dialect == "postgresql" else r"^(\d{3})_.*(?<!\.pg)\.sql$"
    found: dict[int, Path] = {}
    if not directory.is_dir():
        return []
    for entry in sorted(directory.iterdir()):
        m = re.match(pattern, entry.name)
        if not m:
            continue
        version = int(m.group(1))
        if version == 0:
            raise RuntimeError(f"{entry}: extension migrations start at 001")
        prior = found.get(version)
        if prior is not None:
            raise RuntimeError(
                f"Duplicate extension migration {version:03d}: {prior.name} and {entry.name}"
            )
        found[version] = entry
    return sorted(found.items())


def _placeholder(db: DatabasePool) -> str:
    return "%s" if db.dialect == "postgresql" else "?"


def _read_version(conn: Any, db: DatabasePool, namespace: str) -> int:
    row = conn.execute(
        f"SELECT version FROM _extension_schema WHERE namespace = {_placeholder(db)}",
        (namespace,),
    ).fetchone()
    if row is None:
        return 0
    return int(row["version"] if isinstance(row, Mapping) else row[0])


def current_version(db: DatabasePool, namespace: str) -> int:
    """The namespace's watermark (0 when none). Unlocked: a hint, re-read before applying."""
    with db.transaction() as conn:
        _lock(conn, db)
        conn.execute(_CREATE_TABLE)
        return _read_version(conn, db, namespace)


def _lock(conn: Any, db: DatabasePool) -> None:
    # SQLite: db.transaction() is BEGIN IMMEDIATE, which already holds the write lock.
    if db.dialect == "postgresql":
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_PG_LOCK_KEY,))


def _set_version(conn: Any, db: DatabasePool, namespace: str, version: int) -> None:
    p = _placeholder(db)
    conn.execute(
        f"INSERT INTO _extension_schema (namespace, version) VALUES ({p}, {p}) "
        "ON CONFLICT (namespace) DO UPDATE SET version = excluded.version",
        (namespace, version),
    )


def _statements(sql: str) -> list[str]:
    out: list[str] = []
    for part in _SQL_STMT_RE.split(sql):
        lines = part.strip().splitlines()
        while lines and (not lines[0].strip() or lines[0].lstrip().startswith("--")):
            lines.pop(0)
        cleaned = "\n".join(lines).strip().rstrip(";").strip()
        if cleaned:
            out.append(cleaned)
    return out


def apply(db: DatabasePool, spec: ExtensionMigrations) -> int:
    """Apply ``spec``'s pending files; return the namespace's version afterwards."""
    if not _NAMESPACE_RE.match(spec.namespace):
        raise ValueError(f"invalid extension migration namespace {spec.namespace!r}")
    files = discover(spec.directory, db.dialect)
    version = current_version(db, spec.namespace)
    for file_version, path in files:
        if file_version <= version:
            continue
        statements = _statements(path.read_text(encoding="utf-8"))
        with db.transaction() as conn:
            _lock(conn, db)
            # Another process may have applied it since we last looked.
            version = _read_version(conn, db, spec.namespace)
            if file_version <= version:
                continue
            logger.info("extension migration %s/%s", spec.namespace, path.name)
            for stmt in statements:
                conn.execute(stmt)
            _set_version(conn, db, spec.namespace, file_version)
        version = file_version
    return version


def run_extension_migrations(db: DatabasePool) -> None:
    """Apply every loaded extension's migrations, in extension name order."""
    from octop.infra.extensions import extension_hooks  # noqa: PLC0415

    seen: dict[str, str] = {}
    for ext_name, hook in extension_hooks("migrations"):
        spec = hook()
        if not isinstance(spec, ExtensionMigrations):
            raise TypeError(f"extension {ext_name!r}: migrations() must return ExtensionMigrations")
        owner = seen.setdefault(spec.namespace, ext_name)
        if owner != ext_name:
            raise RuntimeError(
                f"extensions {owner!r} and {ext_name!r} both claim namespace {spec.namespace!r}"
            )
        apply(db, spec)
