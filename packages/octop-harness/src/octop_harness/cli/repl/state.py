"""Session state shared across the REPL lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionState:
    """Mutable state for a single REPL session.

    Shared between loop, handler, and toolbar. Updated after each agent turn.
    """

    session_id: str
    model: str
    agent_cfg: dict[str, Any]
    current_agent: str = "main"
    input_tokens: int = 0
    output_tokens: int = 0
    max_tokens: int = 128_000
    last_elapsed: float = 0.0
    thread_model_override: str | None = None
    _stop_generation: Any = field(default=None, repr=False, compare=False)

    @property
    def total_tokens(self) -> int:
        """Total tokens consumed this session."""
        return self.input_tokens + self.output_tokens

    def update_usage(self, *, input_tokens: int, output_tokens: int, elapsed: float) -> None:
        """Update token counters after an agent turn."""
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.last_elapsed = elapsed

    def bind_stop(self, callback: Any) -> None:
        self._stop_generation = callback

    def request_stop(self) -> None:
        if self._stop_generation is not None:
            self._stop_generation()
