"""Custom completers for the REPL: slash commands + @file references."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

if TYPE_CHECKING:
    from collections.abc import Iterable

    from prompt_toolkit.completion import CompleteEvent


def _build_slash_commands() -> list[str]:
    """Build slash command list dynamically from the registered command registry."""
    from octop_harness.cli.repl.commands import _ALIASES, COMMANDS
    from octop_harness.cli.repl.slash_router import runtime_command_names

    names = set(COMMANDS) | runtime_command_names()
    return sorted([f"/{name}" for name in names] + [f"/{alias}" for alias in _ALIASES])


# Slash commands available in the REPL — generated from the command registry
# NOTE: populated lazily on first access via SlashCompleter to avoid circular import
# (completer.py ← input.py ← loop.py ← repl/__init__.py ← commands.py)
SLASH_COMMANDS: list[str] = []


class FileRefCompleter(Completer):
    """Completer triggered by ``@`` — suggests project file paths.

    Uses a cached file listing (refreshed every ``cache_ttl`` seconds)
    from ``git ls-files`` or a directory walk fallback.
    """

    def __init__(self, cwd: Path, cache_ttl: float = 5.0) -> None:
        self._cwd = cwd
        self._cache_ttl = cache_ttl
        self._file_cache: list[str] | None = None
        self._cache_time: float = 0.0

    def get_completions(
        self,
        document: Document,
        complete_event: CompleteEvent,
    ) -> Iterable[Completion]:
        """Yield file path completions when cursor follows ``@``."""
        text_before = document.text_before_cursor

        # Find the last @ that starts a file reference
        at_pos = text_before.rfind("@")
        if at_pos < 0:
            return

        # Only trigger if @ is at start or preceded by whitespace
        if at_pos > 0 and not text_before[at_pos - 1].isspace():
            return

        prefix = text_before[at_pos + 1 :]  # text after @

        # Don't complete if prefix looks like an email (has @ before last @)
        if "@" in prefix:
            return

        files = self._get_files()
        start_position = -len(prefix)

        for path in files:
            if not prefix or path.startswith(prefix) or _basename(path).startswith(prefix):
                # Show basename as display, full path as completion
                yield Completion(
                    path,
                    start_position=start_position,
                    display_meta=_file_type_hint(path),
                )

    def _get_files(self) -> list[str]:
        """Get the cached file list, refreshing if stale."""
        now = time.time()
        if self._file_cache is None or (now - self._cache_time) > self._cache_ttl:
            from octop_harness.cli.ui.file_ref import list_project_files

            self._file_cache = list_project_files(self._cwd)
            self._cache_time = now
        return self._file_cache


class SlashCompleter(Completer):
    """Completer for slash commands at the start of input."""

    def get_completions(
        self,
        document: Document,
        complete_event: CompleteEvent,
    ) -> Iterable[Completion]:
        """Yield slash command completions when input starts with /."""
        text = document.text_before_cursor.lstrip()

        if not text.startswith("/"):
            return

        # Populate lazily on first use to avoid circular import at module load time.
        # (completer ← input ← loop ← repl/__init__ ← commands)
        if not SLASH_COMMANDS:
            SLASH_COMMANDS.extend(_build_slash_commands())

        for cmd in SLASH_COMMANDS:
            if cmd.startswith(text):
                yield Completion(
                    cmd,
                    start_position=-len(text),
                )


class MergedCompleter(Completer):
    """Combines SlashCompleter and FileRefCompleter based on context.

    - Input starts with ``/`` → slash commands
    - Input contains ``@`` at cursor → file paths
    - Otherwise → no completions
    """

    def __init__(self, cwd: Path) -> None:
        self._slash = SlashCompleter()
        self._file_ref = FileRefCompleter(cwd)

    def get_completions(
        self,
        document: Document,
        complete_event: CompleteEvent,
    ) -> Iterable[Completion]:
        text = document.text_before_cursor

        # Slash commands: only at start of input
        stripped = text.lstrip()
        if stripped.startswith("/"):
            yield from self._slash.get_completions(document, complete_event)
            return

        # File references: when @ is present
        if "@" in text:
            yield from self._file_ref.get_completions(document, complete_event)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _basename(path: str) -> str:
    """Extract filename from a path string."""
    idx = path.rfind("/")
    return path[idx + 1 :] if idx >= 0 else path


def _file_type_hint(path: str) -> str:
    """Short type hint for display in completion menu."""
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    hints = {
        "py": "Python",
        "ts": "TypeScript",
        "tsx": "React TSX",
        "js": "JavaScript",
        "json": "JSON",
        "md": "Markdown",
        "yaml": "YAML",
        "yml": "YAML",
        "toml": "TOML",
        "rs": "Rust",
        "go": "Go",
        "sql": "SQL",
        "sh": "Shell",
        "css": "CSS",
        "html": "HTML",
        "png": "Image",
        "jpg": "Image",
        "svg": "SVG",
    }
    return hints.get(ext, ext)


__all__ = ["SLASH_COMMANDS", "FileRefCompleter", "MergedCompleter", "SlashCompleter"]
