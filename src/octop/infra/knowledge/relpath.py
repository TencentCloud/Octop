"""Relative paths for knowledge-base folders and documents."""

from __future__ import annotations


def normalize_kb_path(raw: str | None) -> str:
    """Return a workspace-style relative path (no leading slash, no ``..``)."""
    text = str(raw or "").replace("\\", "/").strip()
    if not text or text == ".":
        return ""
    if text.startswith("/"):
        text = text[1:]
    parts = [part for part in text.split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        raise ValueError("invalid knowledge document path")
    return "/".join(parts)


def path_basename(path: str) -> str:
    normalized = normalize_kb_path(path)
    if not normalized:
        return ""
    return normalized.rsplit("/", 1)[-1]


def path_parent(path: str) -> str:
    normalized = normalize_kb_path(path)
    if "/" not in normalized:
        return ""
    return normalized.rsplit("/", 1)[0]


def path_is_direct_child(path: str, prefix: str) -> bool:
    """True when *path* is an immediate child of folder *prefix* (empty = root)."""
    normalized = normalize_kb_path(path)
    parent = normalize_kb_path(prefix)
    if not normalized or normalized == parent:
        return False
    if not parent:
        return "/" not in normalized
    if not normalized.startswith(parent + "/"):
        return False
    rest = normalized[len(parent) + 1 :]
    return bool(rest) and "/" not in rest


def ancestor_dirs(path: str) -> list[str]:
    """Parent folder paths from root toward the file, excluding the file itself."""
    normalized = normalize_kb_path(path)
    if "/" not in normalized:
        return []
    parts = normalized.split("/")[:-1]
    out: list[str] = []
    acc: list[str] = []
    for part in parts:
        acc.append(part)
        out.append("/".join(acc))
    return out
