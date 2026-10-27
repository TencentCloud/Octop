"""Shared SkillHub host and zip/HTTP safety limits.

Skill search/download lives in :mod:`octop.infra.skills.skillhub_market`.
Expert skillset marketplace lives in
:mod:`octop.infra.agents.experts.skillhub_market` and reuses these limits.
The skill market origin is ``SKILL_MARKET_ORIGIN`` (see ``docs/skill-market.md``).
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

DEFAULT_SKILLHUB_HOST = "https://api.skillhub.cn"
MAX_HTTP_BYTES = 32 * 1024 * 1024
MAX_ZIP_ENTRIES = 2_000
MAX_ZIP_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 100.0
HTTP_READ_CHUNK = 64 * 1024


def skill_market_origin(override: str | None = None) -> str:
    """Skill market origin: scheme, host, and optional port.

    ``override`` wins, then ``SKILL_MARKET_ORIGIN``, then
    ``DEFAULT_SKILLHUB_HOST``. A bare host is treated as ``https://``.
    A path, query, or userinfo on the value is dropped. An unusable value
    raises ``ValueError`` carrying the raw string.
    """
    raw = (override or "").strip() or os.environ.get("SKILL_MARKET_ORIGIN", "").strip()
    raw = raw or DEFAULT_SKILLHUB_HOST
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    hostname = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise ValueError(raw)
    host = f"[{hostname}]" if ":" in hostname else hostname
    origin = f"{parsed.scheme}://{host}"
    if parsed.port is not None:
        origin = f"{origin}:{parsed.port}"
    return origin


__all__ = [
    "DEFAULT_SKILLHUB_HOST",
    "HTTP_READ_CHUNK",
    "MAX_HTTP_BYTES",
    "MAX_ZIP_COMPRESSION_RATIO",
    "MAX_ZIP_ENTRIES",
    "MAX_ZIP_UNCOMPRESSED_BYTES",
    "skill_market_origin",
]
