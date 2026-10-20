"""Automatic discovery of source memory stores (requirement 1).

Scans the default paths of all known hosts on this machine and lists
migratable memory stores.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any

from octop_memory.operations.migration.portable.models import (
    HOST_KIND_AGENT,
    HOST_KIND_HERMES,
    HOST_KIND_OCTOPMEMORY,
    HOST_SCAN_PATTERNS,
    SourceInfo,
)

logger = logging.getLogger(__name__)

# Signature table names used to identify a octop-memory schema (without the namespace prefix)
_SCHEMA_TABLES = {"raw_events", "atoms", "entities", "journal"}

# SQL used to try reading schema_version
_SCHEMA_VERSION_SQL = "SELECT value FROM {ns}_meta WHERE key = 'schema_version' LIMIT 1"

# OpenClaw config file consulted for the plugin's configured namespace.
DEFAULT_OPENCLAW_CONFIG = Path("~/.openclaw/openclaw.json")


def _openclaw_plugin_config(config_path: Path | None = None) -> dict[str, Any]:
    """The ``plugins.entries.octopmemory.config`` block from openclaw.json, or {}."""
    import json

    path = (config_path or DEFAULT_OPENCLAW_CONFIG).expanduser()
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    plugins = cfg.get("plugins") if isinstance(cfg, dict) else None
    entries = plugins.get("entries") if isinstance(plugins, dict) else None
    entry = entries.get("octopmemory") if isinstance(entries, dict) else None
    entry_cfg = entry.get("config") if isinstance(entry, dict) else None
    return entry_cfg if isinstance(entry_cfg, dict) else {}


def configured_openclaw_namespace(config_path: Path | None = None) -> str | None:
    """Namespace the installed OpenClaw plugin is configured to read, if any.

    The OpenClaw plugin opens exactly one namespace
    (``plugins.entries.octopmemory.config.namespace`` in ``openclaw.json``);
    memory adopted into any other namespace lands in a SQLite file the plugin
    never opens and is invisible to the agent. Callers defaulting a target
    namespace for the openclaw host must therefore prefer this value over any
    generated name.
    """
    namespace = _openclaw_plugin_config(config_path).get("namespace")
    if isinstance(namespace, str) and namespace.strip():
        return namespace.strip()
    return None


def configured_openclaw_db_path(config_path: Path | None = None) -> str | None:
    """SQLite path the installed OpenClaw plugin is configured with, if any.

    Sandboxed deployments (openclaw-security/bwrap) relocate the store under
    ``~/.openclaw`` via ``config.db_path`` — adopting/doctoring against the
    hardcoded ``~/.octopmemory`` default would then hit a file the plugin
    never opens. Callers must prefer this value when the target namespace
    matches the configured one.
    """
    db_path = _openclaw_plugin_config(config_path).get("db_path")
    if isinstance(db_path, str) and db_path.strip():
        return db_path.strip()
    return None


def _infer_agent_name(db_path: Path, host_kind: str) -> str:
    """Infer the agent/host name from the db path."""
    if host_kind == HOST_KIND_AGENT:
        # ~/.octop/agents/<NAME>/memory.sqlite or ~/.octop-harness/<NAME>/memory.sqlite
        return db_path.parent.name
    if host_kind == HOST_KIND_HERMES:
        return "hermes"
    if host_kind == HOST_KIND_OCTOPMEMORY:
        return db_path.parent.name
    return db_path.parent.name


def _list_namespaces(conn: sqlite3.Connection) -> list[str]:
    """List all octop-memory namespaces from a sqlite connection.

    Namespaces are identified by looking for {ns}_raw_events tables.
    """
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_raw_events'").fetchall()
    except sqlite3.Error:
        logger.warning("failed to list namespaces", exc_info=True)
        return []

    namespaces = []
    for row in rows:
        table_name = row[0]
        # Strip the _raw_events suffix to get the namespace
        ns = table_name[: -len("_raw_events")]
        if ns:
            namespaces.append(ns)
    return namespaces


def _count_table(conn: sqlite3.Connection, table_name: str) -> int:
    """Safely count rows in a table; returns 0 on failure."""
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        return int(row[0]) if row else 0
    except (sqlite3.Error, TypeError, ValueError):
        logger.warning("failed to count table %s", table_name, exc_info=True)
        return 0


def _get_schema_version(conn: sqlite3.Connection, ns: str) -> int:
    """Read the schema_version for a namespace; returns 0 on failure."""
    try:
        row = conn.execute(f"SELECT value FROM {ns}_meta WHERE key = 'schema_version' LIMIT 1").fetchone()
        return int(row[0]) if row else 0
    except (sqlite3.Error, TypeError, ValueError):
        logger.warning("failed to read schema_version for %s", ns, exc_info=True)
        return 0


def _probe_db(db_path: Path, host_kind: str) -> list[SourceInfo]:
    """Open a SQLite file and return the SourceInfo list for every namespace within it.

    Uses a read-only connection; on failure, prints a warning and returns an empty list.
    """
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
    except (sqlite3.Error, OSError) as exc:
        print(f"[portable] warning: cannot open {db_path}: {exc}", file=sys.stderr)
        return []

    try:
        namespaces = _list_namespaces(conn)
        if not namespaces:
            return []

        results = []
        agent_name = _infer_agent_name(db_path, host_kind)

        for ns in namespaces:
            raw_event_count = _count_table(conn, f"{ns}_raw_events")
            atom_count = _count_table(conn, f"{ns}_atoms")
            entity_count = _count_table(conn, f"{ns}_entities")
            journal_count = _count_table(conn, f"{ns}_journal")
            schema_version = _get_schema_version(conn, ns)

            results.append(
                SourceInfo(
                    host_kind=host_kind,
                    db_path=str(db_path),
                    namespace=ns,
                    raw_event_count=raw_event_count,
                    atom_count=atom_count,
                    entity_count=entity_count,
                    journal_count=journal_count,
                    schema_version=schema_version,
                    agent_name=agent_name,
                )
            )
        return results
    except (sqlite3.Error, OSError) as exc:
        logger.warning("error reading %s", db_path, exc_info=True)
        print(f"[portable] warning: error reading {db_path}: {exc}", file=sys.stderr)
        return []
    finally:
        try:
            conn.close()
        except sqlite3.Error:
            logger.warning("failed to close %s", db_path, exc_info=True)


def list_sources(extra_paths: list[tuple[str, str]] | None = None) -> list[SourceInfo]:
    """Scan all known host paths on this machine and return the list of migratable memory stores.

    Args:
        extra_paths: Additional (host_kind, glob_pattern) entries to extend the scan scope.

    Returns:
        The list of all SourceInfo found, with each namespace as a separate entry.
        Stores that cannot be opened or whose schema doesn't match are skipped
        with a stderr warning.
    """
    patterns = list(HOST_SCAN_PATTERNS)
    if extra_paths:
        patterns.extend(extra_paths)

    seen_paths: set[str] = set()
    results: list[SourceInfo] = []

    for host_kind, pattern in patterns:
        expanded = Path(pattern).expanduser()
        # Handle the glob pattern
        name = expanded.name

        # Find the leftmost * to determine where the glob starts
        parts = expanded.parts
        base_parts = []
        glob_started = False
        for part in parts:
            if "*" in part or "?" in part:
                glob_started = True
                break
            base_parts.append(part)

        if not glob_started:
            # No wildcard; check the file directly
            if expanded.exists():
                key = str(expanded)
                if key not in seen_paths:
                    seen_paths.add(key)
                    results.extend(_probe_db(expanded, host_kind))
        else:
            # Has a wildcard; glob starting from the base directory
            base_dir = Path(*base_parts) if base_parts else Path("/")
            # Reconstruct the relative glob pattern
            rel_parts = parts[len(base_parts) :]
            rel_pattern = str(Path(*rel_parts)) if rel_parts else name

            if base_dir.exists():
                for db_path in sorted(base_dir.glob(rel_pattern)):
                    if db_path.is_file():
                        key = str(db_path)
                        if key not in seen_paths:
                            seen_paths.add(key)
                            results.extend(_probe_db(db_path, host_kind))

    return results


__all__ = ["DEFAULT_OPENCLAW_CONFIG", "configured_openclaw_db_path", "configured_openclaw_namespace", "list_sources"]
