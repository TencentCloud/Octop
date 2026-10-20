"""One-click adopt implementation (requirements 3, 4, 6, 7).

Imports a .hmpkg file into a target host. Supports:
- automatic resolution of the target db path
- automatic generation of the target namespace
- host-field rewrite strategy
- idempotency detection (skips if already migrated)
- target db backup + transaction rollback protection
- dry-run mode
"""

from __future__ import annotations

import logging
import shutil
import sys
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from octop_memory.core import Memory
from octop_memory.operations.migration import EXPORT_VERSION
from octop_memory.operations.migration.import_ import OnConflict, import_namespace
from octop_memory.operations.migration.portable.models import (
    HOST_KIND_AGENT,
    HOST_KIND_HERMES,
    HOST_KIND_OCTOPMEMORY,
    HOST_KIND_OPENCLAW,
    HOST_KIND_UNKNOWN,
    HOST_NS_PREFIX,
    PKG_VERSION,
    AdoptSummary,
)
from octop_memory.operations.migration.portable.packer import extract_data_stream, read_manifest
from octop_memory.operations.migration.portable.sources import (
    configured_openclaw_db_path,
    configured_openclaw_namespace,
)
from octop_memory.storage.driver_errors import DRIVER_ERRORS, REPORTABLE_ERRORS

_PKG_ERRORS: tuple[type[BaseException], ...] = (*REPORTABLE_ERRORS, zipfile.BadZipFile)

logger = logging.getLogger(__name__)

HostRewrite = Literal["keep", "target"]

# Backup file retention window (seconds)
_BACKUP_RETAIN_SECONDS = 24 * 3600


def _resolve_target_db_path(host_kind: str, target_namespace: str) -> Path:
    """Resolve the target db path based on the host type and namespace."""
    import os

    if host_kind == HOST_KIND_HERMES:
        hermes_home = os.environ.get("HERMES_HOME", "~/.hermes")
        return Path(hermes_home).expanduser() / "octopmemory" / "memory.sqlite"

    if host_kind == HOST_KIND_AGENT:
        # Infer the agent name from the namespace
        # namespace format: agent_<name>_ or just name
        name = target_namespace.rstrip("_")
        if name.startswith("agent_"):
            name = name[len("agent_") :]
        return Path(f"~/.octop/agents/{name}/memory.sqlite").expanduser()

    if host_kind in (HOST_KIND_OPENCLAW, HOST_KIND_OCTOPMEMORY):
        return Path(f"~/.octopmemory/{target_namespace}/memory.sqlite").expanduser()

    # Unknown host, fall back to the octopmemory path
    return Path(f"~/.octopmemory/{target_namespace}/memory.sqlite").expanduser()


def _build_target_namespace(host_kind: str, source_name: str) -> str:
    """Automatically generate the target namespace per the target host's convention.

    - openclaw -> openclaw__<source-name>
    - hermes   -> hermes__<source-name>
    - agent    -> keep the original name (lowercased)
    """
    prefix = HOST_NS_PREFIX.get(host_kind, "")
    name = source_name.lower().strip("_")
    return f"{prefix}{name}"


def _check_already_adopted(target_memory: Memory, source_namespace: str, packed_at: str) -> str | None:
    """Check whether the target journal already has a migration_in record with the same source_namespace + packed_at.

    Returns the already-migrated timestamp string, or None if not yet migrated.
    """
    try:
        for entry in target_memory.list_journal(limit=10**9):
            if entry.action == "migration_in":
                after = entry.after or {}
                if after.get("source_namespace") == source_namespace and after.get("packed_at") == packed_at:
                    return entry.timestamp.isoformat() if entry.timestamp else packed_at
    except DRIVER_ERRORS:
        logger.warning(
            "failed to check whether %s was already adopted",
            source_namespace,
            exc_info=True,
        )
    return None


def _rewrite_host_in_data(
    data_stream: Any,
    source_host: str,
    target_host: str,
    tmp_path: Path,
) -> Path:
    """Rewrite the RawEvent.host field in data.jsonl.gz to target_host.

    In "target" mode, every RawEvent.host is rewritten to the target host keyword,
    without restricting to records whose host matches source_host (because the actual
    host value may differ from host_kind, e.g. host_kind='agent' but host='octop').

    Returns the path of the rewritten temp file.
    """
    import gzip
    import json

    out_path = tmp_path.with_suffix(".rewritten.jsonl.gz")
    with gzip.open(out_path, "wt", encoding="utf-8") as out_fp:
        for raw_line in data_stream:
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if record.get("table") == "raw_events":
                    data = record.get("data", {})
                    # Rewrite every host to the target host (target mode)
                    data["host"] = target_host
                    record["data"] = data
                out_fp.write(json.dumps(record, ensure_ascii=False) + "\n")
            except (json.JSONDecodeError, TypeError, AttributeError):
                logger.warning("keeping unreadable portable record unchanged", exc_info=True)
                out_fp.write(line + "\n")
    return out_path


def _write_migration_journal(
    target_memory: Memory,
    manifest: dict[str, Any],
    host_rewrite: HostRewrite,
    dry_run: bool,
) -> None:
    """Write the migration_in journal audit record."""
    if dry_run:
        return
    try:
        from octop_memory.types import JournalEntry

        entry = JournalEntry(
            id=f"migration_in_{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
            timestamp=datetime.now(UTC),
            action="migration_in",
            actor="portable",
            after={
                "source_host_kind": manifest.get("source_host_kind"),
                "source_namespace": manifest.get("source_namespace"),
                "packed_at": manifest.get("packed_at"),
                "tool_version": manifest.get("tool_version"),
                "host_rewrite": host_rewrite,
                "originated_from": manifest.get("source_host_kind"),
            },
            note=f"migrated from {manifest.get('source_host_kind')}:{manifest.get('source_namespace')}",
        )
        target_memory.append_journal(entry)
    except DRIVER_ERRORS as exc:
        print(f"[portable] warning: failed to write migration_in journal: {exc}", file=sys.stderr)


def adopt(
    pkg_path: Path | str,
    target_host: str,
    target_namespace: str | None = None,
    *,
    on_conflict: OnConflict = "skip",
    host_rewrite: HostRewrite = "keep",
    dry_run: bool = False,
    target_db_path: Path | str | None = None,
    progress: Callable[[int, int, str], None] | None = None,
) -> AdoptSummary:
    """Import a .hmpkg file into the target host.

    Args:
        pkg_path: path to the .hmpkg file.
        target_host: target host type (agent / openclaw / hermes).
            May include a namespace: 'openclaw:myns'.
        target_namespace: target namespace; auto-generated per host convention if unspecified.
        on_conflict: conflict strategy (skip / replace / raise).
        host_rewrite: host-field rewrite strategy (keep / target).
        dry_run: pre-check only, no actual write.
        target_db_path: directly specify the target db path (overrides auto-resolution,
            mainly for testing).
        progress: progress callback (done, total, phase).

    Returns:
        An AdoptSummary object.
    """
    pkg_path = Path(pkg_path).expanduser()

    # Parse the namespace potentially embedded in target_host
    if ":" in target_host:
        host_kind, ns_override = target_host.split(":", 1)
        if not target_namespace:
            target_namespace = ns_override
    else:
        host_kind = target_host

    host_kind = host_kind.strip().lower()

    if progress:
        progress(0, -1, "reading_manifest")

    # Read and validate the manifest
    try:
        manifest = read_manifest(pkg_path)
    except _PKG_ERRORS as exc:
        raise ValueError(f"failed to read .hmpkg file {pkg_path}: {exc}") from exc

    # Validate pkg_version
    pkg_ver = manifest.get("pkg_version", 1)
    if pkg_ver > PKG_VERSION:
        raise ValueError(
            f"package format version pkg_version={pkg_ver} is newer than the currently "
            f"supported {PKG_VERSION}; please upgrade octop-memory to the latest version."
        )

    # Validate export_version
    export_ver = manifest.get("export_version", EXPORT_VERSION)
    if export_ver != EXPORT_VERSION:
        if export_ver < EXPORT_VERSION:
            print(
                f"[portable] [upgrade] export_version v{export_ver} -> v{EXPORT_VERSION}",
                file=sys.stderr,
            )
        else:
            raise ValueError(
                f"the package's export_version={export_ver} is incompatible with the current "
                f"EXPORT_VERSION={EXPORT_VERSION}; automatic upgrade is not possible, please "
                f"upgrade octop-memory."
            )

    source_namespace = manifest.get("source_namespace", "")
    source_host_kind = manifest.get("source_host_kind", HOST_KIND_UNKNOWN)
    packed_at = manifest.get("packed_at", "")
    agent_name = manifest.get("agent_name", "") or source_namespace.rstrip("_").split("_")[-1]

    # Determine the target namespace. For openclaw, prefer the namespace the
    # installed plugin actually reads (openclaw.json) — a generated
    # openclaw__<source-name> would land in a SQLite file the plugin never
    # opens, making the migrated memory invisible to the agent.
    if not target_namespace and host_kind == HOST_KIND_OPENCLAW:
        configured = configured_openclaw_namespace()
        if configured:
            target_namespace = configured
            print(
                f"[portable] using namespace {configured!r} from the OpenClaw plugin config; "
                "pass host:namespace to override.",
                file=sys.stderr,
            )
    if not target_namespace:
        target_namespace = _build_target_namespace(host_kind, agent_name or source_namespace)

    # Determine the target db path. For openclaw, when adopting into the
    # namespace the installed plugin reads, prefer the plugin's configured
    # db_path: sandboxed deployments (openclaw-security/bwrap) relocate the
    # store under ~/.openclaw, and the ~/.octopmemory fallback would be a
    # file the plugin never opens.
    if target_db_path is not None:
        resolved_db_path = Path(target_db_path).expanduser()
    else:
        resolved_db_path = None
        if host_kind == HOST_KIND_OPENCLAW and target_namespace == configured_openclaw_namespace():
            configured_db = configured_openclaw_db_path()
            if configured_db:
                resolved_db_path = Path(configured_db).expanduser()
                print(
                    f"[portable] using db_path {configured_db!r} from the OpenClaw plugin config.",
                    file=sys.stderr,
                )
        if resolved_db_path is None:
            resolved_db_path = _resolve_target_db_path(host_kind, target_namespace)
    assert resolved_db_path is not None

    if progress:
        progress(0, -1, "checking")

    # Open the target Memory (dry_run also needs to check the already-migrated state)
    resolved_db_path.parent.mkdir(parents=True, exist_ok=True)
    target_memory = Memory(
        namespace=target_namespace,
        backend="sqlite",
        backend_config={"db_path": str(resolved_db_path)},
    )

    # Idempotency detection: check whether it has already been migrated
    already_at = _check_already_adopted(target_memory, source_namespace, packed_at)
    if already_at:
        print(
            f"[portable] already adopted at {already_at}, skipping.",
            file=sys.stderr,
        )
        return AdoptSummary(
            target_namespace=target_namespace,
            target_db_path=str(resolved_db_path),
            applied=0,
            skipped=0,
            dry_run=dry_run,
            already_adopted=True,
            already_adopted_at=already_at,
        )

    # Count rows with an empty/unknown host (used for the dry_run hint)
    unknown_host_count = 0
    if dry_run or host_rewrite == "target":
        try:
            stream = extract_data_stream(pkg_path)
            import json as _json

            for raw_line in stream:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = _json.loads(line)
                    if record.get("table") == "raw_events":
                        h = record.get("data", {}).get("host", "")
                        if not h or h in ("", "unknown"):
                            unknown_host_count += 1
                except (_json.JSONDecodeError, TypeError, AttributeError):
                    logger.warning("skipping unreadable portable record while counting hosts", exc_info=True)
            stream.close()
        except _PKG_ERRORS:
            logger.warning("failed to scan portable package for unknown hosts", exc_info=True)

    if dry_run:
        # dry_run: pre-check only, no write
        total_rows = manifest.get("total_rows", 0)
        if unknown_host_count > 0:
            print(
                f"[portable] dry-run: {unknown_host_count} raw_events have an empty/unknown host field, "
                f"consider using --host-rewrite=target as a fallback.",
                file=sys.stderr,
            )
        return AdoptSummary(
            target_namespace=target_namespace,
            target_db_path=str(resolved_db_path),
            applied=total_rows,
            skipped=0,
            dry_run=True,
        )

    # Back up the target db (if it already has non-empty data)
    backup_path: Path | None = None
    if resolved_db_path.exists() and resolved_db_path.stat().st_size > 0:
        backup_path = resolved_db_path.with_suffix(".pre-migrate.bak")
        try:
            shutil.copy2(str(resolved_db_path), str(backup_path))
        except OSError as exc:
            print(f"[portable] warning: failed to create backup {backup_path}: {exc}", file=sys.stderr)
            backup_path = None

    if progress:
        progress(0, manifest.get("total_rows", -1), "importing")

    # Extract the data stream (may need host rewriting)
    tmp_rewritten: Path | None = None
    try:
        if host_rewrite == "target" and source_host_kind != HOST_KIND_UNKNOWN:
            # Rewrite the host field
            stream = extract_data_stream(pkg_path)
            tmp_rewritten = pkg_path.with_suffix(".tmp_rewrite")
            rewritten_path = _rewrite_host_in_data(
                stream,
                source_host=source_host_kind,
                target_host=host_kind,
                tmp_path=tmp_rewritten,
            )
            stream.close()
            import_path = rewritten_path
        else:
            # Use the raw data as-is, decompressing to a temp file first
            stream = extract_data_stream(pkg_path)
            tmp_rewritten = pkg_path.with_suffix(".tmp_import.jsonl.gz")
            import gzip as _gzip

            with _gzip.open(tmp_rewritten, "wt", encoding="utf-8") as out_fp:
                for line in stream:
                    out_fp.write(line)  # type: ignore[arg-type]
            stream.close()
            import_path = tmp_rewritten

        # Perform the import
        try:
            import_summary = import_namespace(
                target_memory,
                import_path,
                on_conflict=on_conflict,
            )
        except _PKG_ERRORS as exc:
            # Import failed, roll back
            if backup_path and backup_path.exists():
                try:
                    shutil.copy2(str(backup_path), str(resolved_db_path))
                    print(
                        f"[portable] import failed, restored the target db from backup {backup_path}.",
                        file=sys.stderr,
                    )
                except OSError as restore_exc:
                    print(
                        f"[portable] failed to restore backup: {restore_exc}, backup file: {backup_path}",
                        file=sys.stderr,
                    )
            raise ValueError(
                f"import failed: {exc}\n" + (f"backup file: {backup_path}" if backup_path else "")
            ) from exc

    finally:
        if tmp_rewritten and tmp_rewritten.exists():
            try:
                tmp_rewritten.unlink()
            except OSError:
                logger.warning("failed to remove temp file %s", tmp_rewritten, exc_info=True)
        # Clean up the rewritten file
        if tmp_rewritten:
            rewritten = tmp_rewritten.with_suffix(".rewritten.jsonl.gz")
            if rewritten.exists():
                try:
                    rewritten.unlink()
                except OSError:
                    logger.warning("failed to remove rewritten file %s", rewritten, exc_info=True)

    # Write the migration_in journal entry
    _write_migration_journal(target_memory, manifest, host_rewrite, dry_run=False)

    # Clean up expired backups (older than 24h)
    if backup_path and backup_path.exists():
        try:
            bak_age = datetime.now(UTC).timestamp() - backup_path.stat().st_mtime
            if bak_age > _BACKUP_RETAIN_SECONDS:
                backup_path.unlink()
        except OSError:
            logger.warning("failed to remove expired backup %s", backup_path, exc_info=True)

    total_applied = import_summary.total_applied
    total_skipped = import_summary.total_skipped

    if progress:
        progress(total_applied, manifest.get("total_rows", total_applied), "done")

    return AdoptSummary(
        target_namespace=target_namespace,
        target_db_path=str(resolved_db_path),
        applied=total_applied,
        skipped=total_skipped,
        errors=import_summary.errors,
        dry_run=False,
        applied_by_table=import_summary.applied,
        skipped_by_table=import_summary.skipped,
    )


__all__ = ["HostRewrite", "adopt"]
