"""Shared market origins and zip/HTTP safety limits.

Skill search/download lives in :mod:`octop.infra.skills.skillhub_market` and
reads ``SKILL_MARKET_ORIGIN``. Skillset metadata and skillset packages live in
:mod:`octop.infra.agents.experts.skillhub_market` and read ``SKILLSET_ORIGIN``.
See ``docs/skill-market.md``.
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

    ``override`` wins, then ``SKILL_MARKET_ORIGIN``, then the public default.
    A bare host is treated as ``https://``. A path, query, or userinfo on the
    value is dropped. An unusable value raises ``ValueError`` carrying the raw
    string.
    """
    raw = (override or "").strip() or os.environ.get("SKILL_MARKET_ORIGIN", "").strip()
    return _http_origin(raw)


def skillset_origin(override: str | None = None) -> str:
    """Skillset origin: scheme, host, and optional port.

    ``override`` wins, then ``SKILLSET_ORIGIN``, then the public default.
    Parsing matches :func:`skill_market_origin`.
    """
    raw = (override or "").strip() or os.environ.get("SKILLSET_ORIGIN", "").strip()
    return _http_origin(raw)


def _http_origin(raw: str) -> str:
    value = raw or DEFAULT_SKILLHUB_HOST
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    hostname = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise ValueError(raw or value)
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
    "skillset_origin",
]
