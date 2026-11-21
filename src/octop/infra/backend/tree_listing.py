"""Single-level directory listings for workspace and Admin storage trees."""

from __future__ import annotations

from typing import Any


def is_listing_self(entry_path: str, *, parent: str) -> bool:
    """True when *entry_path* is the directory currently being listed."""
    text = str(entry_path or "").strip().replace("\\", "/").rstrip("/")
    base = str(parent or "").strip().replace("\\", "/").rstrip("/")
    if not text or text in {".", "./"}:
        return True
    if base in {"", ".", "./", "/"}:
        return text in {".", "./", "/"}
    return text == base or text == base.lstrip("/")


def dedupe_tree_rows(rows: list[dict[str, Any]], *, parent: str) -> list[dict[str, Any]]:
    """Keep one row per path; drop the listed directory itself."""
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in rows:
        raw = str(row.get("path") or "").replace("\\", "/").strip()
        if is_listing_self(raw, parent=parent):
            continue
        is_dir = bool(row.get("is_dir")) or raw.endswith("/")
        norm = raw.rstrip("/") or ("." if parent in {"", "."} else parent)
        if is_listing_self(norm, parent=parent):
            continue
        existing = merged.get(norm)
        if existing is not None:
            if is_dir and not existing.get("is_dir"):
                existing["is_dir"] = True
            continue
        merged[norm] = {**row, "path": norm, "is_dir": is_dir}
        order.append(norm)
    return [merged[key] for key in order]


__all__ = ["dedupe_tree_rows", "is_listing_self"]
