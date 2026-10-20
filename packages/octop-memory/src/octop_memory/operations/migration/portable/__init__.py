"""octop_memory.operations.migration.portable — cross-host memory migration service.

Public API::

    from octop_memory.operations.migration.portable import list_sources, pack, adopt, doctor

The four function signatures map one-to-one onto the CLI arguments and
return structured result objects whose fields exactly match the REST
response payloads.

Typical usage::

    # List every memory store on this machine that can be migrated
    sources = list_sources()

    # Pack the memory of octop agent my-agent
    summary = pack("agent:my-agent", out="~/my-agent.hmpkg")

    # Adopt the package on an OpenClaw host
    result = adopt("~/my-agent.hmpkg", "openclaw")

    # Verify the migration result
    report = doctor("openclaw", compare_with="~/my-agent.hmpkg")
"""

from __future__ import annotations

from octop_memory.operations.migration.portable.adopter import HostRewrite, adopt
from octop_memory.operations.migration.portable.doctor import doctor
from octop_memory.operations.migration.portable.models import (
    HMPKG_MAGIC,
    HOST_DEFAULT_PATHS,
    HOST_KIND_AGENT,
    HOST_KIND_HERMES,
    HOST_KIND_OCTOPMEMORY,
    HOST_KIND_OPENCLAW,
    HOST_KIND_UNKNOWN,
    HOST_KINDS,
    HOST_NS_PREFIX,
    HOST_SCAN_PATTERNS,
    PKG_VERSION,
    AdoptSummary,
    DoctorCheckResult,
    DoctorReport,
    PackSummary,
    SourceInfo,
)
from octop_memory.operations.migration.portable.packer import pack, read_manifest
from octop_memory.operations.migration.portable.sources import (
    configured_openclaw_db_path,
    configured_openclaw_namespace,
    list_sources,
)

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
    # Constants
    "PKG_VERSION",
    "AdoptSummary",
    "DoctorCheckResult",
    "DoctorReport",
    "HostRewrite",
    "PackSummary",
    # Data models
    "SourceInfo",
    "adopt",
    "configured_openclaw_db_path",
    "configured_openclaw_namespace",
    "doctor",
    # The four main functions
    "list_sources",
    "pack",
    # Helper functions
    "read_manifest",
]
