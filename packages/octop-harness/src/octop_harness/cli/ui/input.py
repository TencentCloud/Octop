"""prompt_toolkit based input handling for the REPL."""

from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent

from octop_harness.cli.ui.completer import MergedCompleter

if TYPE_CHECKING:
    from pathlib import Path


def create_prompt_session(
    history_file: Path | None = None,
    cwd: Path | None = None,
) -> PromptSession[str]:
    """Create a prompt_toolkit session with multi-line support and completion.

    Key bindings:
        - Enter: submit input
        - Escape+Enter or Alt+Enter: insert newline (multi-line)

    Args:
        history_file: Path to persist input history.
        cwd: Working directory for @file completions. Defaults to Path.cwd().
    """
    from pathlib import Path as _Path

    if cwd is None:
        cwd = _Path.cwd()

    completer = MergedCompleter(cwd=cwd)

    bindings = KeyBindings()

    @bindings.add("escape", "enter")
    def _newline(event: KeyPressEvent) -> None:
        """Insert a newline (multi-line input)."""
        event.current_buffer.insert_text("\n")

    history = FileHistory(str(history_file)) if history_file else None

    return PromptSession(
        completer=completer,
        key_bindings=bindings,
        history=history,
        multiline=False,  # Enter submits; Escape+Enter for newline
    )
