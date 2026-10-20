"""Data model definitions for the portable module.

Defines all the structured data types needed by the cross-host memory
migration service; field names match the REST response bodies and can be
serialized to JSON directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Package format version constant
# ---------------------------------------------------------------------------

PKG_VERSION = 1
"""Package format version number stored in manifest.json, independent of the
underlying EXPORT_VERSION. Used to track evolution of the manifest structure
itself."""

HMPKG_MAGIC = b"PK"
"""Magic number for hmpkg files (the zip format's PK header)."""

# ---------------------------------------------------------------------------
# Host kind and default path mapping
# ---------------------------------------------------------------------------

HOST_KIND_AGENT = "agent"
HOST_KIND_OPENCLAW = "openclaw"
HOST_KIND_HERMES = "hermes"
HOST_KIND_OCTOPMEMORY = "octopmemory"
HOST_KIND_UNKNOWN = "unknown"

HOST_KINDS = (HOST_KIND_AGENT, HOST_KIND_OPENCLAW, HOST_KIND_HERMES, HOST_KIND_OCTOPMEMORY)

# Default db path templates per host (using the {name} placeholder)
HOST_DEFAULT_PATHS: dict[str, str] = {
    HOST_KIND_AGENT: "~/.octop/agents/{name}/memory.sqlite",
    HOST_KIND_OPENCLAW: "~/.octopmemory/{name}/memory.sqlite",
    HOST_KIND_HERMES: "~/.hermes/octopmemory/memory.sqlite",
    HOST_KIND_OCTOPMEMORY: "~/.octopmemory/{name}/memory.sqlite",
}

# Scan glob patterns per host (used by list-sources)
HOST_SCAN_PATTERNS: list[tuple[str, str]] = [
    # (host_kind, glob_pattern)
    (HOST_KIND_AGENT, "~/.octop/agents/*/memory.sqlite"),
    (HOST_KIND_AGENT, "~/.octop-harness/*/memory.sqlite"),
    (HOST_KIND_HERMES, "~/.hermes/octopmemory/memory.sqlite"),
    (HOST_KIND_OCTOPMEMORY, "~/.octopmemory/*/memory.sqlite"),
    # Sandbox-friendly openclaw location (setup default since 0.9.2): the
    # openclaw-security/bwrap sandbox only binds ~/.openclaw back into
    # plugin subprocesses, so that's where new stores live.
    (HOST_KIND_OPENCLAW, "~/.openclaw/octopmemory/*/memory.sqlite"),
]

# Namespace prefix convention per host
HOST_NS_PREFIX: dict[str, str] = {
    HOST_KIND_OPENCLAW: "openclaw__",
    HOST_KIND_HERMES: "hermes__",
    HOST_KIND_AGENT: "",
    HOST_KIND_OCTOPMEMORY: "",
}

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class SourceInfo:
    """Information about one migratable memory-store source.

    Corresponds to each line of output from the list-sources command, and
    each JSON record returned by GET /api/memory/portable/sources.
    """

    host_kind: str
    """Host kind: agent / openclaw / hermes / octopmemory / unknown"""

    db_path: str
    """Absolute path of the SQLite file"""

    namespace: str
    """Table prefix (namespace), e.g. agent_zywztd_"""

    raw_event_count: int = 0
    atom_count: int = 0
    entity_count: int = 0
    journal_count: int = 0
    schema_version: int = 0

    agent_name: str = ""
    """Agent/host name inferred from the path, e.g. my-agent"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "host_kind": self.host_kind,
            "db_path": self.db_path,
            "namespace": self.namespace,
            "raw_event_count": self.raw_event_count,
            "atom_count": self.atom_count,
            "entity_count": self.entity_count,
            "journal_count": self.journal_count,
            "schema_version": self.schema_version,
            "agent_name": self.agent_name,
        }


@dataclass
class PackSummary:
    """Result summary of a pack() operation.

    Corresponds to the response body of
    POST /api/agents/{agent_id}/memory/portable/pack.
    """

    source_namespace: str
    out_path: str
    total_rows: int
    file_size_bytes: int
    row_counts: dict[str, int] = field(default_factory=dict)
    packed_at: datetime | None = None
    tool_version: str = ""
    schema_version: int = 0
    pkg_version: int = PKG_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_namespace": self.source_namespace,
            "out_path": self.out_path,
            "total_rows": self.total_rows,
            "file_size_bytes": self.file_size_bytes,
            "row_counts": self.row_counts,
            "packed_at": self.packed_at.isoformat() if self.packed_at else None,
            "tool_version": self.tool_version,
            "schema_version": self.schema_version,
            "pkg_version": self.pkg_version,
        }


@dataclass
class AdoptSummary:
    """Result summary of an adopt() operation.

    Corresponds to the response body of
    POST /api/agents/{agent_id}/memory/portable/adopt.
    """

    target_namespace: str
    target_db_path: str
    applied: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False
    already_adopted: bool = False
    already_adopted_at: str | None = None
    applied_by_table: dict[str, int] = field(default_factory=dict)
    skipped_by_table: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_namespace": self.target_namespace,
            "target_db_path": self.target_db_path,
            "applied": self.applied,
            "skipped": self.skipped,
            "errors": self.errors,
            "dry_run": self.dry_run,
            "already_adopted": self.already_adopted,
            "already_adopted_at": self.already_adopted_at,
            "applied_by_table": self.applied_by_table,
            "skipped_by_table": self.skipped_by_table,
        }


@dataclass
class DoctorCheckResult:
    """Result of a single doctor check."""

    name: str
    """Check name"""

    passed: bool
    hint: str = ""
    """Suggested fix when the check fails"""

    detail: str = ""
    """Extra detail information"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "hint": self.hint,
            "detail": self.detail,
        }


@dataclass
class DoctorReport:
    """Full report of a doctor() operation.

    Corresponds to the response body of
    POST /api/agents/{agent_id}/memory/portable/doctor.
    """

    host_kind: str
    namespace: str
    db_path: str
    checks: list[DoctorCheckResult] = field(default_factory=list)
    raw_event_count: int = 0
    atom_count: int = 0
    entity_count: int = 0
    journal_count: int = 0

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "host_kind": self.host_kind,
            "namespace": self.namespace,
            "db_path": self.db_path,
            "checks": [c.to_dict() for c in self.checks],
            "all_passed": self.all_passed,
            "raw_event_count": self.raw_event_count,
            "atom_count": self.atom_count,
            "entity_count": self.entity_count,
            "journal_count": self.journal_count,
        }


__all__ = [
    "HMPKG_MAGIC",
    "HOST_DEFAULT_PATHS",
    "HOST_KINDS",
    "HOST_KIND_AGENT",
    "HOST_KIND_HERMES",
    "HOST_KIND_OCTOPMEMORY",
    "HOST_KIND_OPENCLAW",
    "HOST_KIND_UNKNOWN",
    "HOST_NS_PREFIX",
    "HOST_SCAN_PATTERNS",
    "PKG_VERSION",
    "AdoptSummary",
    "DoctorCheckResult",
    "DoctorReport",
    "PackSummary",
    "SourceInfo",
]
