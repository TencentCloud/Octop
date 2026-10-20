"""CLI-specific configuration schema (not passed to octop-harness core)."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Literal


@dataclass
class CliConfig:
    """CLI behavior settings.

    These control the terminal experience only and are never
    passed to the octop-harness core library.
    """

    theme: Literal["dark", "light"] = "dark"
    stream: bool = True
    show_token_usage: bool = True
    show_thinking: bool = False
    show_tool_calls: bool = True
    max_history_display: int = 50
    keybindings: Literal["emacs", "vi"] = "emacs"
    default_command: str = "chat"
    context_window_tokens: int = 128_000

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "theme": self.theme,
            "stream": self.stream,
            "show_token_usage": self.show_token_usage,
            "show_thinking": self.show_thinking,
            "show_tool_calls": self.show_tool_calls,
            "max_history_display": self.max_history_display,
            "keybindings": self.keybindings,
            "default_command": self.default_command,
            "context_window_tokens": self.context_window_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CliConfig:
        """Deserialize from a dict, ignoring unknown keys."""
        known_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)
