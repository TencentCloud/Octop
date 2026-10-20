"""prompt_toolkit bottom toolbar formatter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from octop_harness.cli.ui.token_bar import _format_k

if TYPE_CHECKING:
    from octop_harness.cli.repl.state import SessionState


def format_toolbar(state: SessionState) -> str:
    """Format the bottom toolbar string for prompt_toolkit.

    Layout: ` model │ session: xxxxxxxx │ ctx: 3.5k/128k (2%) │ last: 2.1s`
    """
    parts: list[str] = [
        f" {state.current_agent}",
        state.model,
        f"session: {state.session_id[:8]}",
    ]

    # Context window usage (always show)
    total_k = _format_k(state.total_tokens)
    max_k = _format_k(state.max_tokens)
    pct = int(state.total_tokens / state.max_tokens * 100) if state.max_tokens > 0 else 0
    parts.append(f"ctx: {total_k}/{max_k} ({pct}%)")

    if state.last_elapsed > 0:
        parts.append(f"last: {state.last_elapsed:.1f}s")

    return " │ ".join(parts)
