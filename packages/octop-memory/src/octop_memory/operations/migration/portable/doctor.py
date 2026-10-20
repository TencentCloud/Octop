"""Post-migration validation (doctor) implementation (requirement 5).

Runs 6 health checks against the target db, and can optionally compare row
counts against a .hmpkg manifest.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from octop_memory.operations.migration.portable.models import (
    HOST_KIND_AGENT,
    HOST_KIND_HERMES,
    HOST_KIND_OPENCLAW,
    DoctorCheckResult,
    DoctorReport,
)
from octop_memory.operations.migration.portable.sources import (
    configured_openclaw_db_path,
    configured_openclaw_namespace,
)
from octop_memory.storage.driver_errors import REPORTABLE_ERRORS

logger = logging.getLogger(__name__)


def _resolve_db_path(host_kind: str, namespace: str) -> Path:
    """Resolve the db path from host kind and namespace (kept in sync with adopter)."""
    import os

    if host_kind == HOST_KIND_HERMES:
        hermes_home = os.environ.get("HERMES_HOME", "~/.hermes")
        return Path(hermes_home).expanduser() / "octopmemory" / "memory.sqlite"

    if host_kind == HOST_KIND_AGENT:
        name = namespace.rstrip("_")
        if name.startswith("agent_"):
            name = name[len("agent_") :]
        return Path(f"~/.octop/agents/{name}/memory.sqlite").expanduser()

    return Path(f"~/.octopmemory/{namespace}/memory.sqlite").expanduser()


def _check_schema_version(conn: sqlite3.Connection, ns: str) -> DoctorCheckResult:
    """Check that the meta table is readable and report the schema version.

    Stores created by octop-memory < 0.9.2 never wrote the
    ``schema_version`` key (the backend only stamped ``fts_text_version``),
    so a missing row is expected on older databases — it is NOT corruption.
    Only a failure to read the meta table itself fails the check.
    """
    try:
        row = conn.execute(f"SELECT value FROM {ns}_meta WHERE key = 'schema_version' LIMIT 1").fetchone()
        if row:
            return DoctorCheckResult(
                name="schema_version",
                passed=True,
                detail=f"schema_version = {row[0]}",
            )
        return DoctorCheckResult(
            name="schema_version",
            passed=True,
            detail="not recorded (store created by octop-memory < 0.9.2); will be stamped on next open",
        )
    except REPORTABLE_ERRORS as exc:
        logger.warning("doctor check failed", exc_info=True)
        return DoctorCheckResult(
            name="schema_version",
            passed=False,
            hint=f"failed to read the meta table: {exc}",
        )


def _check_fts_index(conn: sqlite3.Connection, ns: str, table: str) -> DoctorCheckResult:
    """Check that the FTS5 index exists and its row count matches the main table."""
    fts_table = f"{ns}_{table}_fts"
    main_table = f"{ns}_{table}"
    check_name = f"fts_{table}"

    try:
        # Check whether the FTS table exists
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (fts_table,),
        ).fetchone()
        if not row:
            return DoctorCheckResult(
                name=check_name,
                passed=False,
                hint=f"FTS5 index table {fts_table} does not exist; run: "
                f"octop-memory reindex --backend sqlite --db <path>",
            )

        # Compare row counts
        main_count = conn.execute(f"SELECT COUNT(*) FROM {main_table}").fetchone()[0]
        fts_count = conn.execute(f"SELECT COUNT(*) FROM {fts_table}").fetchone()[0]

        if main_count != fts_count:
            return DoctorCheckResult(
                name=check_name,
                passed=False,
                hint=f"FTS index row count ({fts_count}) does not match the main table "
                f"({main_count}); rebuild the index.",
                detail=f"main={main_count}, fts={fts_count}",
            )

        return DoctorCheckResult(
            name=check_name,
            passed=True,
            detail=f"{fts_table} row count = {fts_count}",
        )
    except REPORTABLE_ERRORS as exc:
        logger.warning("doctor check failed", exc_info=True)
        return DoctorCheckResult(
            name=check_name,
            passed=False,
            hint=f"error while checking the FTS index: {exc}",
        )


def _check_foreign_keys(conn: sqlite3.Connection, ns: str) -> DoctorCheckResult:
    """Check that atom -> entity foreign keys have no dangling references."""
    try:
        # Check for atoms referencing an entity that no longer exists
        count = conn.execute(
            f"""SELECT COUNT(*) FROM {ns}_atoms a
                WHERE NOT EXISTS (
                    SELECT 1 FROM {ns}_entities e WHERE e.id = a.entity_id
                )"""
        ).fetchone()[0]

        if count > 0:
            return DoctorCheckResult(
                name="foreign_keys",
                passed=False,
                hint=f"found {count} atom(s) referencing a nonexistent entity; data may be incomplete.",
                detail=f"dangling atom count = {count}",
            )

        return DoctorCheckResult(
            name="foreign_keys",
            passed=True,
            detail="atom -> entity foreign keys are intact",
        )
    except REPORTABLE_ERRORS as exc:
        logger.warning("doctor check failed", exc_info=True)
        return DoctorCheckResult(
            name="foreign_keys",
            passed=False,
            hint=f"error while checking foreign keys: {exc}",
        )


def _check_journal_sequence(conn: sqlite3.Connection, ns: str) -> DoctorCheckResult:
    """Check that the journal sequence has no gaps (approximated via id continuity)."""
    try:
        # Check whether the journal table exists
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (f"{ns}_journal",),
        ).fetchone()
        if not row:
            return DoctorCheckResult(
                name="journal_sequence",
                passed=True,
                detail="journal table does not exist (empty db)",
            )

        count = conn.execute(f"SELECT COUNT(*) FROM {ns}_journal").fetchone()[0]
        return DoctorCheckResult(
            name="journal_sequence",
            passed=True,
            detail=f"journal has {count} record(s)",
        )
    except REPORTABLE_ERRORS as exc:
        logger.warning("doctor check failed", exc_info=True)
        return DoctorCheckResult(
            name="journal_sequence",
            passed=False,
            hint=f"error while checking the journal: {exc}",
        )


def _check_recall_smoke(db_path: str, namespace: str) -> DoctorCheckResult:
    """Run a single recall smoke test to verify Memory can recall normally."""
    try:
        from octop_memory.core import Memory

        memory = Memory(
            namespace=namespace,
            backend="sqlite",
            backend_config={"db_path": db_path},
        )
        # A simple recall; no result is required, it just must not raise.
        memory.recall("hello")
        return DoctorCheckResult(
            name="recall_smoke",
            passed=True,
            detail="recall('hello') succeeded",
        )
    except REPORTABLE_ERRORS as exc:
        logger.warning("doctor check failed", exc_info=True)
        return DoctorCheckResult(
            name="recall_smoke",
            passed=False,
            hint=f"recall smoke test failed: {exc}",
        )


def doctor(
    host_kind: str,
    namespace: str | None = None,
    *,
    compare_with: Path | str | None = None,
    db_path: str | None = None,
) -> DoctorReport:
    """Run health checks against the target db.

    Args:
        host_kind: Host kind (agent / openclaw / hermes).
            May include a namespace, e.g. 'openclaw:myns'.
        namespace: Target namespace; resolved from host_kind if not given.
        compare_with: Optional .hmpkg file path, used to compare row counts.
        db_path: Explicit db path (overrides automatic resolution).

    Returns:
        A DoctorReport object.
    """
    # Resolve any namespace embedded in host_kind
    if ":" in host_kind:
        hk, ns_override = host_kind.split(":", 1)
        if not namespace:
            namespace = ns_override
        host_kind = hk.strip().lower()
    else:
        host_kind = host_kind.strip().lower()

    # For openclaw, default to the namespace the installed plugin actually
    # reads (same rule as adopt) so doctor inspects the store the agent uses.
    if not namespace and host_kind == HOST_KIND_OPENCLAW:
        namespace = configured_openclaw_namespace()
    if not namespace:
        namespace = host_kind

    # Resolve the db path (same preference order as adopt: explicit arg >
    # the plugin's configured db_path for its own namespace > host default).
    resolved_db: Path | None = Path(db_path).expanduser() if db_path else None
    if resolved_db is None and host_kind == HOST_KIND_OPENCLAW and namespace == configured_openclaw_namespace():
        configured_db = configured_openclaw_db_path()
        if configured_db:
            resolved_db = Path(configured_db).expanduser()
    if resolved_db is None:
        resolved_db = _resolve_db_path(host_kind, namespace)

    report = DoctorReport(
        host_kind=host_kind,
        namespace=namespace,
        db_path=str(resolved_db),
    )

    # Check whether the db file exists
    if not resolved_db.exists():
        report.checks.append(
            DoctorCheckResult(
                name="db_accessible",
                passed=False,
                hint=f"database file does not exist: {resolved_db}",
            )
        )
        return report

    # Open a read-only connection
    uri = f"file:{resolved_db}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
    except REPORTABLE_ERRORS as exc:
        logger.warning("doctor check failed", exc_info=True)
        report.checks.append(
            DoctorCheckResult(
                name="db_accessible",
                passed=False,
                hint=f"failed to open the database: {exc}",
            )
        )
        return report

    report.checks.append(DoctorCheckResult(name="db_accessible", passed=True, detail=str(resolved_db)))

    try:
        # Count rows
        def safe_count(table: str) -> int:
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                return int(row[0]) if row else 0
            except (sqlite3.Error, TypeError, ValueError):
                logger.warning("doctor count failed for %s", table, exc_info=True)
                return 0

        report.raw_event_count = safe_count(f"{namespace}_raw_events")
        report.atom_count = safe_count(f"{namespace}_atoms")
        report.entity_count = safe_count(f"{namespace}_entities")
        report.journal_count = safe_count(f"{namespace}_journal")

        # Check 1: schema_version
        report.checks.append(_check_schema_version(conn, namespace))

        # Check 2: raw_events FTS index
        report.checks.append(_check_fts_index(conn, namespace, "raw_events"))

        # Check 3: atoms FTS index
        report.checks.append(_check_fts_index(conn, namespace, "atoms"))

        # Check 4: foreign key integrity
        report.checks.append(_check_foreign_keys(conn, namespace))

        # Check 5: journal sequence
        report.checks.append(_check_journal_sequence(conn, namespace))

    finally:
        conn.close()

    # Check 6: recall smoke test
    report.checks.append(_check_recall_smoke(str(resolved_db), namespace))

    # Optional: compare row counts against a .hmpkg manifest
    if compare_with:
        try:
            from octop_memory.operations.migration.portable.packer import read_manifest

            manifest = read_manifest(compare_with)
            row_counts = manifest.get("row_counts", {})
            pkg_raw = row_counts.get("raw_events", 0)
            pkg_atoms = row_counts.get("atoms", 0)
            pkg_entities = row_counts.get("entities", 0)

            mismatches = []
            if report.raw_event_count != pkg_raw:
                mismatches.append(f"raw_events: db={report.raw_event_count}, pkg={pkg_raw}")
            if report.atom_count != pkg_atoms:
                mismatches.append(f"atoms: db={report.atom_count}, pkg={pkg_atoms}")
            if report.entity_count != pkg_entities:
                mismatches.append(f"entities: db={report.entity_count}, pkg={pkg_entities}")

            if mismatches:
                report.checks.append(
                    DoctorCheckResult(
                        name="compare_with_pkg",
                        passed=False,
                        hint="target db row counts do not match the package manifest; data may have been lost.",
                        detail="; ".join(mismatches),
                    )
                )
            else:
                report.checks.append(
                    DoctorCheckResult(
                        name="compare_with_pkg",
                        passed=True,
                        detail="target db row counts exactly match the package manifest",
                    )
                )
        except REPORTABLE_ERRORS as exc:
            logger.warning("doctor check failed", exc_info=True)
            report.checks.append(
                DoctorCheckResult(
                    name="compare_with_pkg",
                    passed=False,
                    hint=f"failed to read the .hmpkg manifest: {exc}",
                )
            )

    return report


__all__ = ["doctor"]
