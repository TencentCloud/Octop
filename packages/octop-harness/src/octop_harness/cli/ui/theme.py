"""Terminal color schemes for the CLI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    """A set of Rich style strings for terminal rendering.

    Dot prefix colors follow Claude Code's convention:
      - green dot: AI response / success
      - yellow dot: tool calls / actions
      - blue dot: informational / system
      - red dot: errors
      - magenta dot: thinking / reasoning
    """

    name: str
    # --- Dot prefix styles (● before each output section) ---
    dot_ai: str  # AI response / success
    dot_tool: str  # Tool calls / actions
    dot_info: str  # Informational / file refs
    dot_error: str  # Errors
    dot_thinking: str  # Thinking / reasoning

    # --- Content styles ---
    user_prompt_style: str
    assistant_border_style: str
    info_style: str
    error_style: str
    warning_style: str
    token_stats_style: str
    spinner_style: str
    separator_style: str  # Horizontal rule / separator


_DARK_THEME = Theme(
    name="dark",
    dot_ai="bold green",
    dot_tool="bold yellow",
    dot_info="bold blue",
    dot_error="bold red",
    dot_thinking="bold magenta",
    user_prompt_style="bold green",
    assistant_border_style="dim cyan",
    info_style="dim",
    error_style="bold red",
    warning_style="bold yellow",
    token_stats_style="dim italic",
    spinner_style="cyan",
    separator_style="dim",
)

_LIGHT_THEME = Theme(
    name="light",
    dot_ai="bold green",
    dot_tool="bold yellow",
    dot_info="bold blue",
    dot_error="bold red",
    dot_thinking="bold magenta",
    user_prompt_style="bold blue",
    assistant_border_style="dim magenta",
    info_style="dim",
    error_style="bold red",
    warning_style="bold yellow",
    token_stats_style="dim italic",
    spinner_style="magenta",
    separator_style="dim",
)

_THEMES: dict[str, Theme] = {
    "dark": _DARK_THEME,
    "light": _LIGHT_THEME,
}


def get_theme(name: str) -> Theme:
    """Get a theme by name. Falls back to dark if unknown."""
    return _THEMES.get(name, _DARK_THEME)
