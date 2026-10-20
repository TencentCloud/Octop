"""Thinking/waiting animation for the terminal."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from rich.console import Console
from rich.status import Status

if TYPE_CHECKING:
    from octop_harness.cli.ui.theme import Theme


@contextmanager
def thinking_spinner(console: Console, theme: Theme, message: str = "Thinking...") -> Generator[Status, None, None]:
    """Context manager that shows a spinner while waiting for a response."""
    with console.status(
        f"[{theme.spinner_style}]{message}[/]",
        spinner="dots",
    ) as status:
        yield status
