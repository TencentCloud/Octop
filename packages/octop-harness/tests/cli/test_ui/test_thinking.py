"""Tests for ThinkingRenderer."""

from io import StringIO

from rich.console import Console

from octop_harness.cli.ui.theme import get_theme
from octop_harness.cli.ui.thinking import ThinkingRenderer


def test_thinking_renderer_feed_accumulates() -> None:
    console = Console(file=StringIO(), force_terminal=True)
    theme = get_theme("dark")
    renderer = ThinkingRenderer(console, theme)
    renderer.start()
    renderer.feed("Hello ")
    renderer.feed("world")
    assert renderer.content == "Hello world"
    renderer.collapse()


def test_thinking_renderer_collapse_prints_summary() -> None:
    output = StringIO()
    console = Console(file=output, force_terminal=True)
    theme = get_theme("dark")
    renderer = ThinkingRenderer(console, theme)
    renderer.start()
    renderer.feed("Some thinking content")
    renderer.collapse()
    printed = output.getvalue()
    assert "Thought for" in printed
    assert "⟡" in printed


def test_thinking_renderer_collapse_without_start() -> None:
    """Collapse is a no-op if never started."""
    console = Console(file=StringIO(), force_terminal=True)
    theme = get_theme("dark")
    renderer = ThinkingRenderer(console, theme)
    # Should not raise
    renderer.collapse()
