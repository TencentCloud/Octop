"""Office preview conversion input whitelist (LibreOffice Kit)."""

from __future__ import annotations

CONVERTIBLE_EXTENSIONS = frozenset(
    {"doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp"}
)
ZIP_CONTAINER_EXTENSIONS = frozenset({"docx", "xlsx", "pptx", "odt", "ods", "odp"})


def extension_of(filename: str) -> str:
    """Lowercase extension without the dot, or empty."""
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in name or name.startswith("."):
        return ""
    return name.rsplit(".", 1)[-1].lower()


def is_convertible_filename(filename: str) -> bool:
    """True when the filename is in the first-wave conversion whitelist."""
    return extension_of(filename) in CONVERTIBLE_EXTENSIONS


def is_zip_container(filename: str) -> bool:
    """True for OOXML / ODF packages whose uncompressed size we can bound."""
    return extension_of(filename) in ZIP_CONTAINER_EXTENSIONS


def trusted_input_name(filename: str) -> str:
    """Snapshot basename using only a whitelisted extension."""
    ext = extension_of(filename)
    if ext not in CONVERTIBLE_EXTENSIONS:
        return "input.bin"
    return f"input.{ext}"
