"""prompt_toolkit bottom toolbar for ``octop chats repl``."""

from __future__ import annotations

from octop.cli.repl.session import ReplSession


def format_repl_toolbar(state: ReplSession) -> str:
    """Format bottom toolbar: agent │ model │ session │ last turn."""
    parts = [
        state.agent_id[:12],
        f"model: {state.model_label}",
        f"mode: {state.conversation_mode or 'craft'}",
        f"session: {state.session_key[:10]}",
    ]
    if state.last_elapsed > 0:
        parts.append(f"last: {state.last_elapsed:.1f}s")
    return " │ ".join(parts)
