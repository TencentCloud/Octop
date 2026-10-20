"""Tests for octop_harness.cli.ui.renderer."""

from io import StringIO

from rich.console import Console

from octop_harness.cli.ui.renderer import StreamRenderer
from octop_harness.cli.ui.theme import get_theme


def test_renderer_accumulates_content() -> None:
    console = Console(file=StringIO(), force_terminal=True)
    theme = get_theme("dark")
    renderer = StreamRenderer(console, theme)

    renderer.start()
    renderer.feed("Hello ")
    renderer.feed("world!")
    renderer.finish()

    assert renderer.content == "Hello world!"


def test_renderer_handles_empty_stream() -> None:
    console = Console(file=StringIO(), force_terminal=True)
    theme = get_theme("dark")
    renderer = StreamRenderer(console, theme)

    renderer.start()
    renderer.finish()

    assert renderer.content == ""


def test_finish_is_idempotent_and_clears_live() -> None:
    """Calling ``finish`` more than once must be safe and must drop the
    Live handle, otherwise an error path that re-enters cleanup leaves
    the terminal in alt-screen mode and stdin gets swallowed."""
    console = Console(file=StringIO(), force_terminal=True)
    renderer = StreamRenderer(console, get_theme("dark"))

    renderer.start()
    renderer.feed("partial output")
    renderer.finish()
    assert renderer._live is None

    # Second call is a no-op, not a crash.
    renderer.finish()
    assert renderer._live is None


def test_finish_swallows_live_stop_errors() -> None:
    """If the underlying ``Live.stop()`` raises (e.g. terminal already
    detached), ``finish`` must still clear ``_live`` so subsequent
    cleanup doesn't get stuck."""

    class _BoomLive:
        def stop(self) -> None:
            raise RuntimeError("boom")

    console = Console(file=StringIO(), force_terminal=True)
    renderer = StreamRenderer(console, get_theme("dark"))
    renderer._live = _BoomLive()  # type: ignore[assignment]

    # Must not raise; must reset state.
    renderer.finish()
    assert renderer._live is None
