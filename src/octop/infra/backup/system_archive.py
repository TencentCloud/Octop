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
from octop.infra.backup.manifest import MANIFEST_VERSION, AgentBackupEntry, BackupManifest
from octop.infra.backup.pg_dump import dump_postgres, restore_postgres
from octop.infra.backup.snapshot import (
    capture_users_from_pool,
    restore_sqlite_into_pool,
    restore_users_into_pool,
    snapshot_sqlite_file,
)
from octop.infra.db.migrate import _current_version, run_migrations
from octop.infra.db.pool import DatabasePool, SqlitePool
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


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _add_dir(tf: tarfile.TarFile, src: Path, arc_root: str) -> None:
    if not src.is_dir():
        return
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src).as_posix()
        tf.add(path, arcname=f"{arc_root}/{rel}")


def create_system_backup(
    *,
    paths: PathLayout,
    agent_rows: list[Any],
    pool: DatabasePool,
    db_config: DatabaseConfig,
) -> tuple[bytes, str]:
    """Build a ``.tar.gz`` archive and return ``(bytes, suggested_filename)``."""
    try:
        schema_version = _current_version(pool)
    except Exception:
        schema_version = 0

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

    agents = [
        AgentBackupEntry(
            agent_id=str(row.agent_id),
            name=str(row.name),
            workspace_included=True,
        )
        for row in agent_rows
    ]
    env_path = env_file_path(paths.root)
    manifest = BackupManifest(
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

    buf = io.BytesIO()
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

        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            tf.add(manifest_path, arcname=_MANIFEST_NAME)
            tf.add(db_dest, arcname=db_arc)
            if paths.config.is_file():
                tf.add(root / _CONFIG_DIR / "config.json", arcname=f"{_CONFIG_DIR}/config.json")
            if env_path.is_file():
                tf.add(root / _CONFIG_DIR / "env", arcname=f"{_CONFIG_DIR}/env")
            for row in agent_rows:
                ws = paths.agent_workspace(str(row.agent_id))
                if ws.is_dir():
                    _add_dir(tf, ws, f"{_WORKSPACES_DIR}/{row.agent_id}")
            if paths.skill_packages_dir.is_dir():
                _add_dir(tf, paths.skill_packages_dir, _SKILL_PACKAGES_DIR)

    filename = f"octop-backup-{_timestamp()}.tar.gz"
    return buf.getvalue(), filename


def _extract_manifest(members: dict[str, bytes]) -> BackupManifest:
    raw = members.get(_MANIFEST_NAME)
    if raw is None:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "backup archive missing manifest.json")
    try:
        manifest = BackupManifest.load_text(raw.decode("utf-8"))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, f"invalid manifest: {exc}") from exc
    if manifest.manifest_version != MANIFEST_VERSION:
        raise OctopError(
            ErrorCode.SLASH_BAD_ARGS,
            f"unsupported manifest version {manifest.manifest_version}",
        )
    return manifest


def _read_tar_members(data: bytes) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            out[member.name.replace("\\", "/")] = extracted.read()
    return out


def _is_migration_backup(manifest: BackupManifest) -> bool:
    """Return True when the backup was produced by the LightClaw migration tool."""
    return manifest.octop_version.endswith(_MIGRATION_VERSION_SUFFIX)


def restore_system_backup(
    data: bytes,
    *,
    paths: PathLayout,
    pool: DatabasePool,
    db_config: DatabaseConfig,
    restore_config: bool = True,
    preserve_users: bool | None = None,
) -> dict[str, Any]:
    """Restore database, workspaces, and optional config from a tar.gz archive.

    ``preserve_users`` controls whether the *current* Octop instance's ``users``
    table is written back after the database is replaced:

    * ``None`` (default) — auto-detect: preserves users when the backup was
      produced by an external migration tool (``octop_version`` ends with
      ``"-migrated-from-lightclaw"``).
    * ``True`` — always preserve the current users (useful for any cross-system
      import where passwords must remain valid).
    * ``False`` — restore the users table as-is from the backup (normal
      same-instance restore).
    """
    members = _read_tar_members(data)
    manifest = _extract_manifest(members)

    # Resolve effective preserve_users flag before touching the DB.
    effective_preserve_users = (
        _is_migration_backup(manifest) if preserve_users is None else preserve_users
    )

    archive_driver = manifest.database_driver or "sqlite"
    if archive_driver != pool.dialect:
        raise OctopError(
            ErrorCode.BACKUP_DRIVER_MISMATCH,
            f"backup database_driver={archive_driver!r} does not match "
            f"runtime dialect={pool.dialect!r}; cross-engine restore is refused",
            status=400,
            details={"archive_driver": archive_driver, "runtime_driver": pool.dialect},
        )

    db_blob = members.get(manifest.db_file)
    if db_blob is None:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "backup archive missing database file")

    # Capture current users before overwriting the DB (only when needed).
    saved_users: list[tuple[object, ...]] = []
    if effective_preserve_users and pool is not None:
        saved_users = capture_users_from_pool(pool)

    with tempfile.TemporaryDirectory() as tmp:
        if pool.dialect == "postgresql":
            dump_path = Path(tmp) / "octop.dump"
            dump_path.write_bytes(db_blob)
            restore_postgres(db_config.postgresql_conninfo(), dump_path)
        else:
            backup_db = Path(tmp) / "octop.db"
            backup_db.write_bytes(db_blob)
            if isinstance(pool, SqlitePool):
                restore_sqlite_into_pool(backup_db, pool)
            else:
                raise OctopError(ErrorCode.INTERNAL_ERROR, "sqlite restore requires SqlitePool")

        if restore_config:
            cfg_blob = members.get(f"{_CONFIG_DIR}/config.json")
            if cfg_blob is not None:
                paths.config.parent.mkdir(parents=True, exist_ok=True)
                paths.config.write_bytes(cfg_blob)
            env_blob = members.get(f"{_CONFIG_DIR}/env")
            if env_blob is not None:
                env_path = env_file_path(paths.root)
                env_path.parent.mkdir(parents=True, exist_ok=True)
                env_path.write_bytes(env_blob)

        # Write back saved users after DB is fully restored.
        if saved_users and pool is not None:
            restore_users_into_pool(pool, saved_users)

        # After a migration restore the secrets table arrives from a foreign
        # system and will not contain a valid JWT secret for this instance.
        # Ensure one exists (create if absent) so the server can start without
        # a manual `_ensure_jwt_secret` call.
        if effective_preserve_users and pool is not None:
            SecretRepo(pool).get_or_create("jwt", lambda: os.urandom(32))

        restored_workspaces = 0
        prefix = f"{_WORKSPACES_DIR}/"
        for name, blob in members.items():
            if not name.startswith(prefix):
                continue
            rel = name[len(prefix) :]
            if "/" not in rel:
                continue
            agent_id, _, file_rel = rel.partition("/")
            if not agent_id or not file_rel:
                continue
            dest = paths.agent_workspace(agent_id) / file_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            restored_workspaces += 1

        # Replace skill-package files wholesale so leftover package dirs cannot
        # outlive a restored database that no longer references them.
        if paths.skill_packages_dir.exists():
            shutil.rmtree(paths.skill_packages_dir)
        paths.skill_packages_dir.mkdir(parents=True, exist_ok=True)
        restored_skill_package_files = 0
        skill_packages_prefix = f"{_SKILL_PACKAGES_DIR}/"
        for name, blob in members.items():
            if not name.startswith(skill_packages_prefix):
                continue
            rel = name[len(skill_packages_prefix) :]
            if not rel:
                continue
            dest = paths.skill_packages_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            restored_skill_package_files += 1

        # LightClaw migration exports (and older Octop backups) may ship schema v1
        # without columns added in later migrations (e.g. cron_jobs.mcp_servers).
        # API restore keeps the process alive, so re-apply migrations on the live pool.
        run_migrations(pool)
        schema_version = _current_version(pool)

    return {
        "schema_version": schema_version,
        "octop_version": manifest.octop_version,
        "agents": len(manifest.agents),
        "workspace_files": restored_workspaces,
        "skill_package_files": restored_skill_package_files,
        "restore_config": restore_config,
        "users_preserved": effective_preserve_users,
        "database_driver": archive_driver,
    }
