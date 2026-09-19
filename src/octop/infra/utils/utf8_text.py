"""Helpers for coercing third-party package bytes into valid UTF-8 text."""

from __future__ import annotations

import logging
from pathlib import Path, PurePosixPath

logger = logging.getLogger(__name__)

# SkillHub has shipped SKILL.md where ``≤`` (U+2264, utf-8 ``e2 89 a4``) was
# corrupted to ``e2 6a 24`` (``âj$``). That single invalid sequence makes strict
# UTF-8 readers raise and breaks skill listing for the whole agent.
_KNOWN_UTF8_REPAIRS: tuple[tuple[bytes, bytes], ...] = ((b"\xe2j$", "≤".encode()),)

_TEXT_SUFFIXES = frozenset(
    {
        ".md",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".csv",
        ".py",
        ".sh",
        ".html",
        ".css",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".xml",
        ".svg",
    }
)


class InvalidSkillManifestEncodingError(ValueError):
    """Raised when a SkillHub ``SKILL.md`` cannot be decoded as UTF-8."""


def looks_like_text_path(path: str) -> bool:
    """Return True when *path* is likely a text file worth UTF-8 coercion."""
    suffix = PurePosixPath(path.replace("\\", "/")).suffix.lower()
    return suffix in _TEXT_SUFFIXES or PurePosixPath(path).name in {
        "SKILL.md",
        "LICENSE",
        "LICENSE.md",
        "README",
        "README.md",
    }


def is_skill_manifest_path(path: str) -> bool:
    """Return True when *path* names a skill manifest (``SKILL.md``)."""
    return PurePosixPath(path.replace("\\", "/")).name == "SKILL.md"


def repair_known_utf8_corruption(data: bytes) -> bytes | None:
    """Return repaired bytes for known corruptions, or None if unchanged/unrepairable."""
    try:
        data.decode("utf-8")
        return None
    except UnicodeDecodeError:
        pass

    repaired = data
    for bad, good in _KNOWN_UTF8_REPAIRS:
        if bad in repaired:
            repaired = repaired.replace(bad, good)
    if repaired == data:
        return None
    try:
        repaired.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return repaired


def coerce_utf8_text_bytes(data: bytes, *, path: str = "") -> bytes:
    """Return *data* as valid UTF-8 bytes for non-manifest text files.

    Binary-looking paths are returned unchanged. Text paths that are already
    valid UTF-8 are returned unchanged. Otherwise known SkillHub corruptions are
    repaired; residual invalid sequences are replaced so callers never persist
    undecodable auxiliary text files.

    For ``SKILL.md``, use :func:`require_utf8_skill_manifest` instead — manifests
    must not be silently replaced.
    """
    if path and not looks_like_text_path(path):
        return data
    if path and is_skill_manifest_path(path):
        return require_utf8_skill_manifest(data, path=path)
    try:
        data.decode("utf-8")
        return data
    except UnicodeDecodeError:
        pass

    known = repair_known_utf8_corruption(data)
    if known is not None:
        logger.warning(
            "repaired invalid UTF-8 in package entry %s",
            path or "<bytes>",
        )
        return known

    text = data.decode("utf-8", errors="replace")
    repaired = text.encode("utf-8")
    logger.warning("replaced invalid UTF-8 bytes in package entry %s", path or "<bytes>")
    return repaired


def require_utf8_skill_manifest(data: bytes, *, path: str = "SKILL.md") -> bytes:
    """Decode/repair a skill manifest, or raise if it is still not valid UTF-8."""
    try:
        data.decode("utf-8")
        return data
    except UnicodeDecodeError:
        pass
    known = repair_known_utf8_corruption(data)
    if known is not None:
        logger.warning("repaired invalid UTF-8 in skill manifest %s", path or "SKILL.md")
        return known
    raise InvalidSkillManifestEncodingError(
        f"Skill manifest is not valid UTF-8: {path or 'SKILL.md'}"
    )


def repair_skill_manifest_file(manifest: Path) -> str | None:
    """Repair a on-disk ``SKILL.md`` for known corruption.

    Returns the decoded text when the file was repaired and rewritten, or
    ``None`` when the file was already valid / missing / unrepairable.
    """
    try:
        raw = manifest.read_bytes()
    except OSError:
        return None
    try:
        raw.decode("utf-8")
        return None
    except UnicodeDecodeError:
        pass
    try:
        fixed = require_utf8_skill_manifest(raw, path=str(manifest))
    except InvalidSkillManifestEncodingError:
        return None
    try:
        text = fixed.decode("utf-8")
        manifest.write_bytes(fixed)
    except (OSError, UnicodeDecodeError):
        return None
    logger.warning("repaired invalid UTF-8 in skill manifest %s", manifest)
    return text
