"""Shared SkillHub host and zip/HTTP safety limits.

Skill search/download lives in :mod:`octop.infra.skills.skillhub_market`.
Expert skillset marketplace lives in
:mod:`octop.infra.agents.experts.skillhub_market` and reuses these limits / host.
"""

from __future__ import annotations

DEFAULT_SKILLHUB_HOST = "https://api.skillhub.cn"
MAX_HTTP_BYTES = 32 * 1024 * 1024
MAX_ZIP_ENTRIES = 2_000
MAX_ZIP_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 100.0
HTTP_READ_CHUNK = 64 * 1024

__all__ = [
    "DEFAULT_SKILLHUB_HOST",
    "HTTP_READ_CHUNK",
    "MAX_HTTP_BYTES",
    "MAX_ZIP_COMPRESSION_RATIO",
    "MAX_ZIP_ENTRIES",
    "MAX_ZIP_UNCOMPRESSED_BYTES",
]
