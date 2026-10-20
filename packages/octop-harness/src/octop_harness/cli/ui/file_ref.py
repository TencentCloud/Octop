"""@-reference parser and resolver for injecting file content into messages."""

from __future__ import annotations

import base64
import mimetypes
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Matches @path/to/file.ext — requires at least one dot (file extension)
# to avoid false positives with @mentions. Allows alphanumeric, /, ., -, _, ~
_AT_REF_PATTERN = re.compile(r"@([\w./\-~][\w./\-~]*\.\w+)")

# Image extensions that should become image_url content blocks
_IMAGE_EXTENSIONS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"})

# Maximum file size for inline injection (100 KB)
MAX_INLINE_BYTES = 100 * 1024


@dataclass
class AtRef:
    """A resolved @-file reference."""

    raw: str  # "@src/main.py"
    path: str  # "src/main.py"
    resolved_path: Path | None = None
    content: str | bytes | None = None
    mime_type: str = "text/plain"
    size: int = 0
    error: str | None = None

    @property
    def is_image(self) -> bool:
        return self.resolved_path is not None and self.resolved_path.suffix.lower() in _IMAGE_EXTENSIONS

    @property
    def is_resolved(self) -> bool:
        return self.error is None and self.content is not None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_project_files(cwd: Path, max_files: int = 5000) -> list[str]:
    """List project files using git ls-files (with os.walk fallback).

    Returns paths relative to ``cwd``.
    """
    files = _git_ls_files(cwd)
    if files is not None:
        return files[:max_files]
    return _walk_files(cwd, max_files)


def parse_at_references(text: str) -> list[AtRef]:
    """Parse @path references from user input text.

    Only matches patterns with a file extension to avoid
    false positives with @mentions like ``@someone``.
    """
    refs: list[AtRef] = []
    seen: set[str] = set()
    for match in _AT_REF_PATTERN.finditer(text):
        path = match.group(1)
        if path not in seen:
            seen.add(path)
            refs.append(AtRef(raw=f"@{path}", path=path))
    return refs


def resolve_references(
    text: str,
    cwd: Path,
) -> tuple[list[dict[str, Any]], list[AtRef]]:
    """Parse and resolve all @references, returning content blocks.

    Args:
        text: The user's raw input text.
        cwd: Working directory for resolving relative paths.

    Returns:
        (content_blocks, resolved_refs):
            - content_blocks: list of dicts suitable for LangChain multipart content
            - resolved_refs: list of AtRef with resolution details (for display)
    """
    refs = parse_at_references(text)
    if not refs:
        return [{"type": "text", "text": text}], []

    # Resolve each reference
    for ref in refs:
        _resolve_single(ref, cwd)

    # Build content blocks
    blocks: list[dict[str, Any]] = []

    # Main text block (with @refs replaced by markers)
    annotated = text
    for ref in refs:
        if ref.is_resolved:
            label = f"[see attached: {ref.path}]"
            annotated = annotated.replace(ref.raw, label)

    blocks.append({"type": "text", "text": annotated})

    # File content blocks
    for ref in refs:
        if not ref.is_resolved:
            continue
        if ref.is_image:
            assert isinstance(ref.content, bytes)
            b64 = base64.b64encode(ref.content).decode("ascii")
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{ref.mime_type};base64,{b64}"},
                }
            )
        else:
            assert isinstance(ref.content, str)
            blocks.append(
                {
                    "type": "text",
                    "text": f'\n<file path="{ref.path}">\n{ref.content}\n</file>\n',
                }
            )

    return blocks, [r for r in refs if r.is_resolved]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_single(ref: AtRef, cwd: Path) -> None:
    """Resolve a single @reference to file content (mutates ref in place)."""
    path = (cwd / ref.path).resolve()

    # Security: don't allow escaping above cwd
    try:
        path.relative_to(cwd.resolve())
    except ValueError:
        ref.error = "path escapes project directory"
        return

    if not path.is_file():
        ref.error = "file not found"
        return

    ref.resolved_path = path
    ref.size = path.stat().st_size

    if ref.size > MAX_INLINE_BYTES:
        ref.error = f"file too large ({ref.size // 1024}KB > {MAX_INLINE_BYTES // 1024}KB)"
        return

    ref.mime_type = mimetypes.guess_type(str(path))[0] or "text/plain"

    if ref.is_image:
        ref.content = path.read_bytes()
    else:
        try:
            ref.content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            ref.error = str(e)


def _git_ls_files(cwd: Path) -> list[str] | None:
    """List tracked + untracked (non-ignored) files via git."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return [f for f in result.stdout.strip().split("\n") if f]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _walk_files(cwd: Path, max_files: int) -> list[str]:
    """Walk directory tree, skipping hidden dirs and common ignore patterns."""
    import os

    skip_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache", "dist", "build"}
    files: list[str] = []
    root_str = str(cwd.resolve())

    for dirpath, dirs, filenames in os.walk(root_str):
        # Prune hidden and ignored directories (in-place)
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root_str)
            files.append(rel)
            if len(files) >= max_files:
                return files

    return files


__all__ = ["AtRef", "list_project_files", "parse_at_references", "resolve_references"]
