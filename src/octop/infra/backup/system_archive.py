"""Full-system backup and restore (database + local agent workspaces + config)."""

from __future__ import annotations

import io
import json
import os
import shutil
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from octop import __version__
from octop.config import DatabaseConfig
from octop.infra.agents.workspace_dir import workspace_dir_from_config_json
from octop.infra.backup.manifest import MANIFEST_VERSION, AgentBackupEntry, BackupManifest
from octop.infra.backup.pg_dump import dump_postgres, restore_postgres
from octop.infra.backup.snapshot import (
    capture_jwt_secret_from_pool,
    capture_users_from_pool,
    infer_owner_user_id,
    prune_users_not_in,
    remap_ownership_to_user,
    restore_jwt_secret_into_pool,
    restore_sqlite_into_pool,
    snapshot_sqlite_file,
    upsert_users_into_pool,
)
from octop.infra.db.migrate import _current_version, run_migrations
from octop.infra.db.pool import DatabasePool, SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.env_file import env_file_path
from octop.infra.utils.paths import PathLayout

_CONFIG_DIR = "config"
_DB_DIR = "db"
_WORKSPACES_DIR = "workspaces"
_SKILL_PACKAGES_DIR = "skill-packages"
_MANIFEST_NAME = "manifest.json"
_SQLITE_DB_ARC = f"{_DB_DIR}/octop.db"
_PG_DUMP_ARC = f"{_DB_DIR}/octop.dump"
_MIGRATION_VERSION_SUFFIX = "-migrated-from-lightclaw"

# Align with workspace zip export; keep backups smaller / faster.
_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".next",
        ".turbo",
        "dist",
        "build",
    }
)


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def suggested_backup_filename() -> str:
    """Canonical basename for a newly created manual backup archive."""
    return f"octop-backup-{_timestamp()}.tar.gz"


def _should_skip_path(rel: Path) -> bool:
    return any(part in _SKIP_DIR_NAMES for part in rel.parts)


def _add_dir(tf: tarfile.TarFile, src: Path, arc_root: str) -> None:
    if not src.is_dir():
        return
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        if _should_skip_path(rel):
            continue
        tf.add(path, arcname=f"{arc_root}/{rel.as_posix()}")


def _build_manifest(
    *,
    paths: PathLayout,
    agent_rows: list[Any],
    pool: DatabasePool,
    db_arc: str,
    database_driver: str,
    database_dump_format: str,
    env_path: Path,
) -> BackupManifest:
    try:
        schema_version = _current_version(pool)
    except Exception:
        schema_version = 0
    agents = [
        AgentBackupEntry(
            agent_id=str(row.agent_id),
            name=str(row.name),
            workspace_included=True,
        )
        for row in agent_rows
    ]
    return BackupManifest(
        manifest_version=MANIFEST_VERSION,
        octop_version=__version__,
        schema_version=schema_version,
        created_at=datetime.now(UTC).isoformat(),
        home=str(paths.root),
        db_file=db_arc,
        database_driver=database_driver,
        database_dump_format=database_dump_format,
        agents=agents,
        includes_config=paths.config.is_file(),
        includes_env=env_path.is_file(),
    )


def create_system_backup(
    *,
    paths: PathLayout,
    agent_rows: list[Any],
    pool: DatabasePool,
    db_config: DatabaseConfig,
    dest: Path,
) -> str:
    """Write a ``.tar.gz`` archive to *dest* (streamed to disk).

    Returns the suggested basename (``octop-backup-….tar.gz``). Callers that
    need a different name should rename/move *dest* afterward.
    """
    if pool.dialect == "postgresql":
        db_arc = _PG_DUMP_ARC
        database_driver = "postgresql"
        database_dump_format = "pg_custom"
    else:
        db_arc = _SQLITE_DB_ARC
        database_driver = "sqlite"
        database_dump_format = "sqlite_file"
        if not isinstance(pool, SqlitePool):
            raise OctopError(ErrorCode.INTERNAL_ERROR, "sqlite backup requires SqlitePool")
        if not pool.path.is_file():
            raise OctopError(ErrorCode.NOT_FOUND, f"database not found: {pool.path}")

    env_path = env_file_path(paths.root)
    manifest = _build_manifest(
        paths=paths,
        agent_rows=agent_rows,
        pool=pool,
        db_arc=db_arc,
        database_driver=database_driver,
        database_dump_format=database_dump_format,
        env_path=env_path,
    )
    filename = suggested_backup_filename()
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".partial")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_dest = root / db_arc
            if pool.dialect == "postgresql":
                dump_postgres(db_config.postgresql_conninfo(), db_dest)
            else:
                assert isinstance(pool, SqlitePool)
                snapshot_sqlite_file(pool.path, db_dest)

            manifest_path = root / _MANIFEST_NAME
            manifest_path.write_text(manifest.to_json(), encoding="utf-8")

            if paths.config.is_file():
                cfg_dir = root / _CONFIG_DIR
                cfg_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(paths.config, cfg_dir / "config.json")
            if env_path.is_file():
                cfg_dir = root / _CONFIG_DIR
                cfg_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(env_path, cfg_dir / "env")

            with tarfile.open(partial, mode="w:gz") as tf:
                tf.add(manifest_path, arcname=_MANIFEST_NAME)
                tf.add(db_dest, arcname=db_arc)
                if paths.config.is_file():
                    tf.add(
                        root / _CONFIG_DIR / "config.json",
                        arcname=f"{_CONFIG_DIR}/config.json",
                    )
                if env_path.is_file():
                    tf.add(root / _CONFIG_DIR / "env", arcname=f"{_CONFIG_DIR}/env")
                for row in agent_rows:
                    ws = workspace_dir_from_config_json(
                        getattr(row, "config_json", None),
                        paths=paths,
                        agent_id=str(row.agent_id),
                    )
                    if ws.is_dir():
                        _add_dir(tf, ws, f"{_WORKSPACES_DIR}/{row.agent_id}")
                if paths.skill_packages_dir.is_dir():
                    _add_dir(tf, paths.skill_packages_dir, _SKILL_PACKAGES_DIR)

        partial.replace(dest)
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    return filename


def _extract_manifest_from_dir(extracted: Path) -> BackupManifest:
    manifest_path = extracted / _MANIFEST_NAME
    if not manifest_path.is_file():
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "backup archive missing manifest.json")
    try:
        manifest = BackupManifest.load_text(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, TypeError, OSError) as exc:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid manifest: {exc}") from exc
    if manifest.manifest_version != MANIFEST_VERSION:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"unsupported manifest version {manifest.manifest_version}",
        )
    return manifest


def _extract_archive(source: Path | bytes, dest_dir: Path) -> None:
    """Extract *source* into *dest_dir* without holding the whole archive in a dict."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(source, bytes):
        with tarfile.open(fileobj=io.BytesIO(source), mode="r:*") as tf:
            # Python 3.12+: refuse path traversal / special files.
            tf.extractall(dest_dir, filter=tarfile.data_filter)
        return
    if not Path(source).is_file():
        raise OctopError(ErrorCode.NOT_FOUND, f"backup not found: {source}")
    with tarfile.open(source, mode="r:*") as tf:
        tf.extractall(dest_dir, filter=tarfile.data_filter)


def _is_migration_backup(manifest: BackupManifest) -> bool:
    """Return True when the backup was produced by the LightClaw migration tool."""
    return manifest.octop_version.endswith(_MIGRATION_VERSION_SUFFIX)


def _iter_extracted_files(root: Path, prefix: str) -> list[tuple[str, Path]]:
    """Return ``(archive-relative-posix, on-disk path)`` under *prefix*."""
    base = root / prefix
    if not base.is_dir():
        return []
    out: list[tuple[str, Path]] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        out.append((rel, path))
    return out


def restore_system_backup(
    source: Path | bytes,
    *,
    paths: PathLayout,
    pool: DatabasePool,
    db_config: DatabaseConfig,
    restore_config: bool = True,
    preserve_users: bool | None = None,
    owner_user_id: int | None = None,
) -> dict[str, Any]:
    """Restore database, workspaces, and optional config from a tar.gz archive.

    *source* may be a filesystem path (preferred) or in-memory bytes (tests / legacy).

    ``preserve_users`` controls whether the *current* Octop instance's login
    credentials (``users`` rows + ``secrets.jwt``) are written back after the
    database is replaced:

    * ``None`` (default) — auto-detect: preserves credentials when the backup
      was produced by an external migration tool (``octop_version`` ends with
      ``"-migrated-from-lightclaw"``).
    * ``True`` — always preserve current users + JWT secret (cross-system
      import where passwords and outstanding sessions must remain valid).
    * ``False`` — restore the users/secrets tables as-is from the backup
      (normal same-instance restore).

    For LightClaw migration archives, ``owner_user_id`` (typically the admin
    performing the restore) receives all imported ``user_id`` ownership. When
    omitted, the first preserved admin (else first preserved user) is used.
    """
    with tempfile.TemporaryDirectory() as tmp:
        extracted = Path(tmp) / "extracted"
        _extract_archive(source, extracted)
        manifest = _extract_manifest_from_dir(extracted)
        is_migration = _is_migration_backup(manifest)

        # Resolve effective preserve_users flag before touching the DB.
        effective_preserve_users = is_migration if preserve_users is None else preserve_users

        archive_driver = manifest.database_driver or "sqlite"
        if archive_driver != pool.dialect:
            raise OctopError(
                ErrorCode.BACKUP_DRIVER_MISMATCH,
                f"backup database_driver={archive_driver!r} does not match "
                f"runtime dialect={pool.dialect!r}; cross-engine restore is refused",
                status=400,
                details={"archive_driver": archive_driver, "runtime_driver": pool.dialect},
            )

        db_path = extracted / manifest.db_file
        if not db_path.is_file():
            raise OctopError(ErrorCode.SLASH_BAD_ARGS, "backup archive missing database file")

        # Capture current login credentials before overwriting the DB (only when needed).
        saved_users: list[tuple[object, ...]] = []
        saved_jwt: bytes | None = None
        if effective_preserve_users and pool is not None:
            saved_users = capture_users_from_pool(pool)
            saved_jwt = capture_jwt_secret_from_pool(pool)

        effective_owner: int | None = None
        if is_migration:
            effective_owner = owner_user_id
            if effective_owner is None:
                effective_owner = infer_owner_user_id(saved_users)
            if effective_owner is not None and saved_users:
                saved_ids = {int(str(row[0])) for row in saved_users}
                if int(effective_owner) not in saved_ids:
                    raise OctopError(
                        ErrorCode.SLASH_BAD_ARGS,
                        f"owner_user_id={effective_owner} is not among current users",
                        status=400,
                    )

        ownership_remap: dict[str, int] | None = None
        if pool.dialect == "postgresql":
            restore_postgres(db_config.postgresql_conninfo(), db_path)
        else:
            if isinstance(pool, SqlitePool):
                restore_sqlite_into_pool(db_path, pool)
            else:
                raise OctopError(ErrorCode.INTERNAL_ERROR, "sqlite restore requires SqlitePool")

        if restore_config:
            cfg_path = extracted / _CONFIG_DIR / "config.json"
            if cfg_path.is_file():
                paths.config.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cfg_path, paths.config)
            env_blob_path = extracted / _CONFIG_DIR / "env"
            if env_blob_path.is_file():
                env_path = env_file_path(paths.root)
                env_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(env_blob_path, env_path)

        # Migration ownership remap must run after the target owner exists and
        # before pruning backup placeholder users (avoids ON DELETE CASCADE).
        if saved_users and pool is not None:
            upsert_users_into_pool(pool, saved_users)
            if is_migration and effective_owner is not None:
                ownership_remap = remap_ownership_to_user(pool, int(effective_owner))
            prune_users_not_in(pool, [row[0] for row in saved_users])

        # Migration backups ship a foreign ``secrets`` table. Prefer the current
        # instance's JWT secret so outstanding sessions stay valid; only seed a
        # fresh key when this instance never had one.
        if effective_preserve_users and pool is not None:
            if saved_jwt is not None:
                restore_jwt_secret_into_pool(pool, saved_jwt)
            else:
                SecretRepo(pool).get_or_create("jwt", lambda: os.urandom(32))

        restored_workspaces = 0
        prefix = f"{_WORKSPACES_DIR}/"
        agent_repo = AgentRepo(pool)
        workspace_by_agent: dict[str, Path] = {}
        for rel, src_file in _iter_extracted_files(extracted, _WORKSPACES_DIR):
            file_rel = rel[len(prefix) :]
            if "/" not in file_rel:
                continue
            agent_id, _, rest = file_rel.partition("/")
            if not agent_id or not rest:
                continue
            dest_root = workspace_by_agent.get(agent_id)
            if dest_root is None:
                row = agent_repo.get(agent_id)
                dest_root = workspace_dir_from_config_json(
                    None if row is None else row.config_json,
                    paths=paths,
                    agent_id=agent_id,
                )
                workspace_by_agent[agent_id] = dest_root
            dest = dest_root / rest
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest)
            restored_workspaces += 1

        # Replace skill-package files wholesale so leftover package dirs cannot
        # outlive a restored database that no longer references them.
        if paths.skill_packages_dir.exists():
            shutil.rmtree(paths.skill_packages_dir)
        paths.skill_packages_dir.mkdir(parents=True, exist_ok=True)
        restored_skill_package_files = 0
        skill_packages_prefix = f"{_SKILL_PACKAGES_DIR}/"
        for rel, src_file in _iter_extracted_files(extracted, _SKILL_PACKAGES_DIR):
            rest = rel[len(skill_packages_prefix) :]
            if not rest:
                continue
            dest = paths.skill_packages_dir / rest
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest)
            restored_skill_package_files += 1

        # LightClaw migration exports (and older Octop backups) may ship schema v1
        # without columns added in later migrations (e.g. cron_jobs.mcp_servers).
        # API restore keeps the process alive, so re-apply migrations on the live pool.
        run_migrations(pool)
        schema_version = _current_version(pool)

    result: dict[str, Any] = {
        "schema_version": schema_version,
        "octop_version": manifest.octop_version,
        "agents": len(manifest.agents),
        "workspace_files": restored_workspaces,
        "skill_package_files": restored_skill_package_files,
        "restore_config": restore_config,
        "users_preserved": effective_preserve_users,
        "jwt_preserved": bool(saved_jwt is not None and effective_preserve_users),
        "database_driver": archive_driver,
    }
    if ownership_remap is not None:
        result["owner_user_id"] = int(effective_owner) if effective_owner is not None else None
        result["ownership_remap"] = ownership_remap
    return result
